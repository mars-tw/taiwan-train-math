"""Offline contract tests. They do not launch macOS, Simulator or a game."""
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import plistlib
import tempfile
import subprocess
import unittest
from unittest import mock
import xml.etree.ElementTree as ET


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, pathlib.Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


driver = load("ashes_driver", "record-ashes-ios-simulator.py")
generator = load("ashes_generator", "create-ashes-simulator-capture-project.py")
UDID = "00000000-0000-4000-8000-000000000001"
OTHER_UDID = "00000000-0000-4000-8000-000000000002"
TYPE_ID = "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro-Max"
RUNTIME = "com.apple.CoreSimulator.SimRuntime.iOS-26-2"


def inventory():
    return {"runtimes": [{"identifier": RUNTIME, "name": "iOS 26.2", "version": "26.2", "isAvailable": True}],
        "devicetypes": [{"identifier": TYPE_ID, "name": "iPhone 17 Pro Max", "minRuntimeVersion": 26 * 65536, "maxRuntimeVersion": 0xFFFFFFFF}],
        "devices": {RUNTIME: []}}


class SimulatorPlanTests(unittest.TestCase):
    def test_exact_baseline_262_selected_even_when_newer_available(self):
        data = inventory()
        data["runtimes"].extend([
            {"identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-3", "name": "iOS 26.3", "version": "26.3", "isAvailable": True},
            {"identifier": "com.apple.CoreSimulator.SimRuntime.iOS-27-0", "name": "iOS 27", "version": "27.0", "isAvailable": False}])
        self.assertEqual(driver.select_plan(data)["runtime"]["version"], "26.2")
        self.assertIn("pinned-known-successful", driver.select_plan(data)["selection"])

    def test_missing_exact_baseline_does_not_fall_back_to_265(self):
        data = inventory()
        data["runtimes"] = [{"identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-5", "name": "iOS 26.5", "version": "26.5", "isAvailable": True}]
        with self.assertRaisesRegex(driver.CaptureFailure, "Pinned baseline iOS 26.2"):
            driver.select_plan(data)

    def test_baseline_version_and_identifier_must_both_match(self):
        for version, identifier in (("26.5", RUNTIME), ("26.2", "com.apple.CoreSimulator.SimRuntime.iOS-26-5"), ("26.2.0", RUNTIME)):
            data = inventory()
            data["runtimes"][0].update(version=version, identifier=identifier)
            with self.assertRaises(driver.CaptureFailure):
                driver.select_plan(data)

    def test_no_obsolete_runtime_or_unavailable_runtime(self):
        data = inventory()
        data["runtimes"][0].update(version="25.4", identifier="com.apple.CoreSimulator.SimRuntime.iOS-25-4")
        with self.assertRaises(driver.CaptureFailure):
            driver.select_plan(data)
        data = inventory()
        data["runtimes"][0]["isAvailable"] = False
        with self.assertRaises(driver.CaptureFailure):
            driver.select_plan(data)

    def test_device_type_runtime_range_must_be_compatible(self):
        data = inventory()
        data["devicetypes"][0]["maxRuntimeVersion"] = 26 * 65536
        with self.assertRaises(driver.CaptureFailure):
            driver.select_plan(data)

    def test_not_an_ipad_or_arbitrary_device(self):
        data = inventory()
        data["devicetypes"][0]["name"] = "iPad Pro 13-inch (M4)"
        with self.assertRaises(driver.CaptureFailure):
            driver.select_plan(data)

    def test_preferred_phone_wins_among_compatible_models(self):
        data = inventory()
        data["devicetypes"].append({"identifier": "com.apple.CoreSimulator.SimDeviceType.iPhone-16-Pro-Max", "name": "iPhone 16 Pro Max"})
        self.assertEqual(driver.select_plan(data)["deviceType"]["name"], "iPhone 17 Pro Max")


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.before = inventory()
        self.plan = driver.select_plan(self.before)
        self.name = driver.OWNER_PREFIX + "a-test-ownership-token"
        self.after = copy.deepcopy(self.before)
        self.after["devices"][RUNTIME].append({"udid": UDID, "name": self.name, "deviceTypeIdentifier": TYPE_ID, "isAvailable": True})

    def test_fresh_owned_uuid_verified(self):
        record = driver.fresh_device(UDID, self.name, self.plan, self.before, self.after)
        self.assertTrue(driver.still_owned(record, self.after))

    def test_existing_uuid_is_never_claimed(self):
        self.before["devices"][RUNTIME] = copy.deepcopy(self.after["devices"][RUNTIME])
        with self.assertRaises(driver.CaptureFailure):
            driver.fresh_device(UDID, self.name, self.plan, self.before, self.after)

    def test_cleanup_refuses_renamed_or_other_type_uuid(self):
        record = driver.fresh_device(UDID, self.name, self.plan, self.before, self.after)
        self.after["devices"][RUNTIME][0]["name"] = "Unrelated user Simulator"
        self.assertFalse(driver.still_owned(record, self.after))
        self.after["devices"][RUNTIME][0]["name"] = self.name
        self.after["devices"][RUNTIME][0]["deviceTypeIdentifier"] = "com.apple.CoreSimulator.SimDeviceType.iPhone-16-Pro-Max"
        self.assertFalse(driver.still_owned(record, self.after))

    def test_cleanup_does_not_match_other_runtime_or_duplicate_uuid(self):
        record = driver.fresh_device(UDID, self.name, self.plan, self.before, self.after)
        self.after["devices"][RUNTIME].append(copy.deepcopy(self.after["devices"][RUNTIME][0]))
        self.assertFalse(driver.still_owned(record, self.after))
        del self.after["devices"][RUNTIME]
        self.assertFalse(driver.still_owned(record, self.after))

    def test_all_booted_and_malformed_ids_rejected(self):
        for value in ("all", "booted", "", "../someone", OTHER_UDID):
            with self.assertRaises(driver.CaptureFailure):
                driver.fresh_device(value, self.name, self.plan, self.before, self.after)

    def test_only_marker_owned_scratch_below_runner_temp(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary)
            own = base / "ashes-simulator-recording-example"
            own.mkdir()
            marker = own / ".owned-capture-scratch"
            marker.write_text("owned-token", encoding="ascii")
            self.assertTrue(driver.safe_scratch(own, base, "owned-token"))
            self.assertFalse(driver.safe_scratch(own, base, "someone-else"))
            self.assertFalse(driver.safe_scratch(base, base, "owned-token"))


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temporary.name)
        self.source = self.base / "frozen"
        self.source.mkdir()
        (self.source / "web").mkdir()
        html = "<html>" + "".join('<' + tag + ' id="' + key + '" aria-label="' + label + '"></' + tag + '>'
            for key, (tag, label) in generator.EXPECTED_CONTROLS.items()) + "</html>"
        self.page = self.source / "web/index.html"
        self.page.write_text(html, encoding="utf-8")
        self.manifest = self.source / "bundle-manifest.json"
        metadata = {"projectId": "ashes-convoy", "appId": generator.APP_ID, "version": "1.0.1", "build": 2, "remoteServer": False,
            "files": [{"path": "index.html", "sha256": driver.sha256(self.page)}]}
        self.manifest.write_text(json.dumps(metadata), encoding="utf-8")
        # Portable synthetic fixture pin is patched only in this test process.
        # The shipping scripts retain the exact real immutable pin below.
        self.pin = mock.patch.object(generator, "MANIFEST_SHA256", driver.sha256(self.manifest))
        self.pin.start()

    def tearDown(self):
        self.pin.stop()
        self.temporary.cleanup()

    def test_generated_swift_preserves_utf8_and_real_inputs(self):
        project = self.base / "tests"
        generator.generate(project, self.source)
        swift = (project / "AshesCaptureUITests.swift").read_text(encoding="utf-8")
        self.assertIn("灰燼護航戰場", swift)
        self.assertIn("開始出勤", swift)
        self.assertIn("app.activate()", swift)
        self.assertNotIn("app.launch()", swift)
        self.assertIn("element.tap()", swift)
        self.assertIn("thenDragTo: last", swift)
        for forbidden in ("evaluateJavaScript", "__test", "launchArguments", "launchEnvironment", "setState("):
            self.assertNotIn(forbidden, swift)

    def test_canvas_input_uses_native_app_viewport_and_actual_screenshot_not_generic_ax(self):
        project = self.base / "tests"
        contract = generator.generate(project, self.source)
        swift = (project / "AshesCaptureUITests.swift").read_text(encoding="utf-8")
        self.assertNotIn('visible(app, "gameCanvas")', swift)
        self.assertNotIn('visible(app, "virtualJoystick")', swift)
        self.assertNotIn("app.webViews", swift)
        self.assertIn("let frame = app.frame", swift)
        self.assertIn("let pauseFrame = pause.frame", swift)
        self.assertIn("frame.contains(pauseFrame)", swift)
        self.assertIn("stage.contains(actualFirstPoint)", swift)
        self.assertIn("abs(frame.width - size.width) < 1", swift)
        self.assertIn("abs(frame.height - size.height) < 1", swift)
        self.assertIn("frame.width > 200, frame.width < 640, frame.height > 500", swift)
        self.assertNotIn("XCUIDevice.shared.orientation == .portrait", swift)
        self.assertIn("ASHES_GEOMETRY_JSON=", swift)
        self.assertLess(swift.index('checkpoint("playing-visible", app: app)'), swift.index("try dragBattlefield(app, pause: playingPause)"))
        self.assertEqual(contract["inputCoordinateContract"]["portraitSourceCssAspect"], [390, 844])
        self.assertEqual(contract["inputCoordinateContract"]["fromNormalizedExpectedCanvas"], [0.5, 0.55])
        self.assertEqual(contract["inputCoordinateContract"]["toNormalizedExpectedCanvas"], [0.72, 0.60])
        self.assertIn("stage.minY + stage.height * 0.60", swift)
        self.assertNotIn("stage.height * 0.38", swift)
        self.assertFalse(contract["inputCoordinateContract"]["canvasAXLabelRequired"])
        self.assertFalse(contract["inputCoordinateContract"]["webViewAXTreeRequired"])
        self.assertFalse(contract["inputCoordinateContract"]["orientationEnumEqualityRequired"])
        self.assertFalse(contract["inputCoordinateContract"]["genericJoystickAXStepUsed"])
        self.assertFalse(contract["inputCoordinateContract"]["gameInputEffectVerified"])

    def test_project_contains_no_game_or_signing_target(self):
        project = self.base / "tests"
        generator.generate(project, self.source)
        data = plistlib.loads((project / "AshesCapture.xcodeproj/project.pbxproj").read_bytes())
        targets = [item for item in data["objects"].values() if item["isa"] == "PBXNativeTarget"]
        self.assertEqual({item["name"] for item in targets}, {"AshesCaptureHost", "AshesCaptureUITests"})
        self.assertFalse(any(item["isa"] == "PBXShellScriptBuildPhase" for item in data["objects"].values()))
        for item in data["objects"].values():
            if item["isa"] == "XCBuildConfiguration":
                settings = item["buildSettings"]
                self.assertEqual(settings["CODE_SIGNING_ALLOWED"], "NO")
                self.assertEqual(settings["SDKROOT"], "iphonesimulator")
                self.assertNotIn("DEVELOPMENT_TEAM", settings)
                self.assertNotIn("PROVISIONING_PROFILE", settings)
        tree = ET.parse(project / "AshesCapture.xcodeproj/xcshareddata/xcschemes/AshesCapture.xcscheme")
        self.assertEqual(tree.find("TestAction").get("shouldUseLaunchSchemeArgsEnv"), "NO")

    def test_source_file_and_source_phase_never_share_identity(self):
        project = self.base / "tests"
        generator.generate(project, self.source)
        data = plistlib.loads((project / "AshesCapture.xcodeproj/project.pbxproj").read_bytes())
        objects = data["objects"]
        generator.validate_object_references(objects)
        source_files = {key: item for key, item in objects.items() if item["isa"] == "PBXFileReference" and item.get("path", "").endswith(".swift")}
        self.assertEqual({item["path"] for item in source_files.values()}, {"CaptureHost.swift", "AshesCaptureUITests.swift"})
        referenced = [objects[item["fileRef"]]["path"] for item in objects.values() if item["isa"] == "PBXBuildFile"]
        self.assertEqual(set(referenced), {"CaptureHost.swift", "AshesCaptureUITests.swift"})
        host_source = next(key for key, item in source_files.items() if item["path"] == "CaptureHost.swift")
        damaged = copy.deepcopy(objects)
        # Reproduce the exact observed native failure: a source phase overwrote
        # the host file identity, leaving a group child/build-file non-file ref.
        damaged[host_source] = {"isa": "PBXSourcesBuildPhase", "files": []}
        with self.assertRaisesRegex(ValueError, "not a file|non-file"):
            generator.validate_object_references(damaged)

    def test_duplicate_pbx_identity_rejected_instead_of_silent_overwrite(self):
        objects = {}
        identity = "3AD83B4745A2471882C93942"
        generator.add_object(objects, identity, "PBXFileReference", path="CaptureHost.swift")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            generator.add_object(objects, identity, "PBXSourcesBuildPhase", files=[])
        self.assertEqual(objects[identity]["isa"], "PBXFileReference")

    def test_generator_cannot_write_inside_frozen_source_or_reuse_target(self):
        with self.assertRaises(ValueError):
            generator.generate(self.source / "injected-tests", self.source)
        project = self.base / "tests"
        generator.generate(project, self.source)
        with self.assertRaises(FileExistsError):
            generator.generate(project, self.source)

    def test_missing_changed_or_duplicate_label_fails_closed(self):
        original = self.page.read_text(encoding="utf-8")
        for value in (original.replace("補給技能", "其它技能"), original.replace('id="touchSkillBtn"', 'id="missing"'),
                      original + '<button id="touchSkillBtn" aria-label="補給技能"></button>'):
            self.page.write_text(value, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "labels|Duplicate"):
                generator.inspect_source(self.source)

    def test_payload_corruption_with_same_label_is_rejected(self):
        self.page.write_text(self.page.read_text(encoding="utf-8") + "corruption", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            generator.inspect_source(self.source)

    def test_manifest_identity_and_demo_flags_are_not_accepted(self):
        original = json.loads(self.manifest.read_text())
        for key, value in (("appId", "tw.mars.other"), ("build", 1), ("version", "1.0.0"), ("remoteServer", True)):
            changed = dict(original, **{key: value})
            self.manifest.write_text(json.dumps(changed), encoding="utf-8")
            with mock.patch.object(generator, "MANIFEST_SHA256", driver.sha256(self.manifest)):
                with self.assertRaises(ValueError):
                    generator.inspect_source(self.source)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.contract = {"actionSequence": generator.ACTION_SEQUENCE, "controls": {key: label for key, (_, label) in generator.EXPECTED_CONTROLS.items()}}
        self.actions = [{"ordinal": index, "action": name, "elapsedSeconds": float(index), "simulator": True,
            **({"foreground": True, "screenshotSha256": "a" * 64} if name.endswith("-visible") else {})}
            for index, name in enumerate(generator.ACTION_SEQUENCE, 1)]
        self.actions[0].update(inputMethod="driver.simctlColdLaunchThenXCTestActivate", driverColdLaunchEvidenceRequired=True,
                               automaticRelaunchAllowed=False, appStateBeforeActivationRaw=4, utcUnixSeconds=100,
                               automaticRelaunchFlagIsPolicyOnly=True, wholeFlowSamePidVerified=False)

    def encode(self, actions):
        return ("\n".join("ASHES_ACTION_JSON=" + json.dumps(item) for item in actions)).encode()

    def test_full_ordered_flow_accepted_and_partial_flow_rejected(self):
        self.assertEqual(len(driver.parse_actions(self.encode(self.actions), self.contract)), 15)
        with self.assertRaises(driver.CaptureFailure):
            driver.parse_actions(self.encode(self.actions[:-1]), self.contract)

    def test_retries_reordering_fake_foreground_or_nan_timing_rejected(self):
        cases = [self.actions + self.actions, list(reversed(self.actions))]
        bad = copy.deepcopy(self.actions)
        bad[1]["foreground"] = False
        cases.append(bad)
        bad = copy.deepcopy(self.actions)
        bad[3]["elapsedSeconds"] = float("nan")
        cases.append(bad)
        for value in cases:
            with self.assertRaises(driver.CaptureFailure):
                driver.parse_actions(self.encode(value), self.contract)

    def test_label_mismatch_rejected(self):
        self.actions[2].update(frozenControl="sortieBtn", label="UNKNOWN")
        with self.assertRaises(driver.CaptureFailure):
            driver.parse_actions(self.encode(self.actions), self.contract)

    def test_actual_xcresult_counts_required(self):
        data = {"totalTestCount": 1, "passedTests": 1, "failedTests": 0, "skippedTests": 0}
        self.assertEqual(driver.result_counts(json.dumps(data).encode())["passedTests"], 1)
        for changed in ({}, dict(data, passedTests=0), dict(data, failedTests=1), dict(data, skippedTests=1), dict(data, totalTestCount=2)):
            with self.assertRaises(driver.CaptureFailure):
                driver.result_counts(json.dumps(changed).encode())

    def test_launch_pid_requires_exact_bundle_and_positive_official_return(self):
        self.assertEqual(driver.parse_cold_launch_pid(b"tw.mars.ashesconvoy: 12345\n"), 12345)
        for invalid in (b"tw.mars.other: 12345", b"tw.mars.ashesconvoy: 0", b"tw.mars.ashesconvoy: -1", b"tw.mars.ashesconvoy: 9999999999", b"no returned PID"):
            with self.assertRaises(driver.CaptureFailure):
                driver.parse_cold_launch_pid(invalid)

    def test_host_pid_liveness_accepts_one_exact_non_zombie_observation(self):
        for state in (b"R", b"S+", b"T", b"U", b"I", b"Ss"):
            self.assertEqual(driver.parse_host_pid_liveness(b" 12345 " + state + b"\n", 12345, 0), state.decode())

    def test_host_pid_liveness_rejects_pid_mismatch_zombie_empty_multiline_and_command_errors(self):
        for raw in (b"12346 S", b"12345 Z", b"12345 Z+", b"12345 SZ", b"", b"12345 ", b"12345 S\n12346 S", b"PID STATE\n12345 S", b"12345 secret-state"):
            with self.assertRaises(driver.CaptureFailure):
                driver.parse_host_pid_liveness(raw, 12345, 0)
        for code in (1, -15, None, False):
            with self.assertRaises(driver.CaptureFailure):
                driver.parse_host_pid_liveness(b"12345 S", 12345, code)
        for timed_out in (True, None, 0):
            with self.assertRaises(driver.CaptureFailure):
                driver.parse_host_pid_liveness(b"12345 S", 12345, 0, timed_out)
        for pid in (0, -1, True, 2147483648):
            with self.assertRaises(driver.CaptureFailure):
                driver.parse_host_pid_liveness(b"12345 S", pid, 0)

    def test_liveness_queries_only_returned_host_pid_and_preserves_pending_launch_facts(self):
        text = pathlib.Path(driver.__file__).read_text(encoding="utf-8")
        launch = text.index('pid = parse_cold_launch_pid(launch_raw)')
        evidence = text.index('facts["normalRecordedColdLaunch"] =', launch)
        query = text.index('commands.run("cold-launch-process-liveness"', evidence)
        verify = text.index('live_state = parse_host_pid_liveness(', query)
        ui = text.index('commands.run("real-continuous-ui-flow"', verify)
        self.assertLess(launch, evidence)
        self.assertLess(evidence, query)
        self.assertLess(query, verify)
        self.assertLess(verify, ui)
        self.assertIn('["/bin/ps", "-p", str(pid), "-o", "pid=", "-o", "state="], 10, check=False)', text)
        self.assertIn('"processLivenessVerified": False', text[evidence:query])
        self.assertIn('"processLivenessVerifiedAtLaunchOnly": False', text[evidence:query])
        self.assertIn('processLivenessVerifiedAtLaunchOnly=True', text[verify:ui])
        self.assertIn('"processLivenessStatus": "pending"', text[evidence:query])
        self.assertIn('DarwinHost.psExactPidAndNonZombieState', text[evidence:query])
        self.assertNotIn('"procinfo"', text)
        self.assertNotIn('"launchctl"', text)
        self.assertIn('"test-without-building"], 480', text)

    def test_launcher_provenance_not_running_or_automatic_relaunch_cannot_pass(self):
        for changes in (dict(appStateBeforeActivationRaw=1), dict(automaticRelaunchAllowed=True), dict(inputMethod="XCUIApplication.launch")):
            actions = copy.deepcopy(self.actions)
            actions[0].update(changes)
            with self.assertRaises(driver.CaptureFailure):
                driver.parse_actions(self.encode(actions), self.contract)

    def test_running_suspended_background_and_foreground_all_accepted_without_pid_interval_claim(self):
        for state in (2, 3, 4):
            actions = copy.deepcopy(self.actions)
            actions[0]["appStateBeforeActivationRaw"] = state
            self.assertEqual(len(driver.parse_actions(self.encode(actions), self.contract)), 15)
        actions = copy.deepcopy(self.actions)
        actions[0]["wholeFlowSamePidVerified"] = True
        with self.assertRaises(driver.CaptureFailure):
            driver.parse_actions(self.encode(actions), self.contract)

    def test_failure_summary_uses_existing_data_and_masks_private_values(self):
        data = {"testFailures": [{"failureText": "Application 'tw.mars.ashesconvoy' does not have a process ID /Users/private-owner/path https://private-token@example.test/a",
                 "testCaseName": "AshesCaptureUITests.testContinuousLaunchSortieAndReturn()", "filePath": "/Users/private-owner/AshesCaptureUITests.swift", "lineNumber": 126},
                {"message": "private key password=DO-NOT-PUBLISH"}]}
        summaries = driver.safe_framework_failure_summaries(json.dumps(data).encode())
        self.assertEqual(summaries[0]["line"], 126)
        self.assertEqual(summaries[0]["generatedFile"], "AshesCaptureUITests.swift")
        self.assertIn("does not have a process ID", summaries[0]["message"])
        for private in ("private-owner", "private-token", "DO-NOT-PUBLISH"):
            self.assertNotIn(private, json.dumps(summaries))
        self.assertEqual(len(driver.safe_framework_failure_summaries(json.dumps({"testFailures": data["testFailures"] * 20}).encode())), 10)

    def test_native_geometry_is_separate_numeric_diagnostic_not_an_action(self):
        geometry = {"nativeAppFrame": [0, 0, 440, 956], "pauseFrame": [380, 60, 40, 40],
                    "screenshotPointSize": [440, 956], "orientationRaw": 1}
        raw = b"ASHES_GEOMETRY_JSON=" + json.dumps(geometry).encode() + b"\n" + self.encode(self.actions)
        self.assertEqual(driver.parse_native_geometry(raw), [geometry])
        self.assertEqual(len(driver.parse_actions(raw, self.contract)), 15)

    def test_native_geometry_discards_secret_strings_unknown_fields_and_unbounded_rows(self):
        geometry = {"nativeAppFrame": [0, 0, 440, 956], "pauseFrame": [380, 60, 40, 40],
                    "screenshotPointSize": [440, 956], "orientationRaw": 1}
        for invalid in (dict(geometry, privateKey="DO-NOT-PUBLISH"), dict(geometry, nativeAppFrame=["DO-NOT-PUBLISH", 0, 440, 956]),
                        dict(geometry, orientationRaw="DO-NOT-PUBLISH")):
            self.assertEqual(driver.parse_native_geometry(b"ASHES_GEOMETRY_JSON=" + json.dumps(invalid).encode()), [])
        raw = (b"ASHES_GEOMETRY_JSON=" + json.dumps(geometry).encode() + b"\n") * 20
        self.assertEqual(len(driver.parse_native_geometry(raw)), 8)
        diagnostic_with_null = dict(geometry, nativeAppFrame=[None, None, 0, 0])
        self.assertEqual(driver.parse_native_geometry(b"ASHES_GEOMETRY_JSON=" + json.dumps(diagnostic_with_null).encode()), [diagnostic_with_null])

    def test_device_ipa_platform_is_rejected(self):
        info = {"CFBundleIdentifier": driver.APP_ID, "CFBundleShortVersionString": "1.0.1", "CFBundleVersion": "2",
            "DTPlatformName": "iphonesimulator", "CFBundleSupportedPlatforms": ["iPhoneSimulator"]}
        self.assertFalse(driver.simulator_platform(info, b"    platform IOSSIMULATOR\n")["sameBinaryAsDeviceIPA"])
        with self.assertRaises(driver.CaptureFailure):
            driver.simulator_platform(info, b"    platform IOS\n")
        info["DTPlatformName"] = "iphoneos"
        with self.assertRaises(driver.CaptureFailure):
            driver.simulator_platform(info, b"    platform IOSSIMULATOR\n")

    def test_mp4_metadata_is_not_content_quality_or_physical_evidence(self):
        data = {"durationSeconds": 30.0, "width": 1320, "height": 2868, "nominalFrameRate": 30.0,
            "videoTrackCount": 1, "audioTrackCount": 0, "contentQualityPassed": False}
        self.assertFalse(driver.metadata_facts(json.dumps(data).encode())["contentQualityPassed"])
        for changed in (dict(data, durationSeconds=0), dict(data, width=0), dict(data, nominalFrameRate=0), dict(data, contentQualityPassed=True)):
            with self.assertRaises(driver.CaptureFailure):
                driver.metadata_facts(json.dumps(changed).encode())

    def test_publisher_secrets_are_not_forwarded_to_subprocesses(self):
        with mock.patch.dict(os.environ, {"PATH": "safe-path", "DEVELOPER_DIR": "safe-xcode", "APPLE_API_PRIVATE_KEY": "never-forward", "GOOGLE_SERVICE_ACCOUNT_JSON": "never-forward"}, clear=True):
            self.assertEqual(driver.child_environment(), {"PATH": "safe-path", "DEVELOPER_DIR": "safe-xcode"})

    def test_exact_real_pins_and_no_fake_video_or_physical_claim(self):
        self.assertEqual(driver.SOURCE_ZIP_SHA256, "1abd7f426e81dc5d15aa84a38d23e6b7672fa8f0da011e1dce4d750dce78efc4")
        self.assertEqual(driver.MANIFEST_SHA256, "b778a8203bd0ff31b10baf5f63d92e3387ced346586dea2526c0254b2d7c8c53")
        self.assertEqual(driver.VERIFIER_SHA256, "e5cd13cc6405ce290ebe539d317daa2c6d5fdc7c3a02f883547e1d9694e737ab")
        text = pathlib.Path(driver.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"physicalDeviceTested": True', text)
        self.assertNotIn('"ApplePhysicalRequirementSatisfied": True', text)
        self.assertNotIn("ffmpeg", text)
        self.assertIn("recorder.send_signal(signal.SIGINT)", text)
        self.assertIn('"recordVideo", "--codec=h264"', text)


class BoundedCommandTests(unittest.TestCase):
    def test_recorder_ack_after_original_thirty_seconds_can_start_within_ninety(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = pathlib.Path(temporary) / "recorder.log"
            log.write_bytes(b"Recorder initialization pending\n")
            recorder = mock.Mock()
            recorder.poll.return_value = None
            def publish_ack(_seconds):
                log.write_bytes(b"Recorder initialization pending\nRecording started\n")
            with mock.patch.object(driver.time, "monotonic", side_effect=[0, 0, 40, 41]), mock.patch.object(driver.time, "sleep", side_effect=publish_ack):
                facts = driver.wait_for_recorder_ack(recorder, log, timeout=90)
            self.assertTrue(facts["recordingStartedAckObserved"])
            self.assertTrue(facts["processAliveAtObservation"])
            self.assertFalse(facts["ackWaitTimedOut"])
            self.assertEqual(facts["elapsedSeconds"], 41)

    def test_live_recorder_and_video_file_without_ack_still_fail_with_safe_stats(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = pathlib.Path(temporary) / "recorder.log"
            log.write_bytes(b"simctl: error: Unable to create output /Users/private-owner/file.mp4 from https://private-token@example.test/video\n")
            (pathlib.Path(temporary) / "video.mp4").write_bytes(b"file-presence-is-not-start-ack")
            recorder = mock.Mock()
            recorder.poll.return_value = None
            with mock.patch.object(driver.time, "monotonic", side_effect=[0, 0, 90, 90]), mock.patch.object(driver.time, "sleep"):
                facts = driver.wait_for_recorder_ack(recorder, log, timeout=90)
            self.assertFalse(facts["recordingStartedAckObserved"])
            self.assertTrue(facts["ackWaitTimedOut"])
            self.assertTrue(facts["processAliveAtObservation"])
            self.assertEqual(facts["privateLogSha256"], hashlib.sha256(log.read_bytes()).hexdigest())
            self.assertFalse(facts["rootCauseConfirmed"])
            self.assertNotIn("private-owner", json.dumps(facts))
            self.assertNotIn("private-token", json.dumps(facts))

    def test_observed_runtime_assertion_stops_only_owned_command_after_cleanup_grace(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = driver.Commands(temporary)
            process = mock.Mock(pid=65432, returncode=-15)
            process.poll.return_value = None
            process.wait.side_effect = [subprocess.TimeoutExpired(["xcodebuild"], 1),
                subprocess.TimeoutExpired(["xcodebuild"], 10), -15]
            def launch(*args, **kwargs):
                kwargs["stdout"].write(b"AshesCaptureUITests.swift:50: error: testFlow: failed - FROZEN_VISIBLE_CONTROL_MISSING_gameCanvas\n")
                kwargs["stdout"].flush()
                return process
            with mock.patch.object(driver.subprocess, "Popen", side_effect=launch), mock.patch.object(driver.os, "killpg", create=True) as kill:
                raw, code = runner.run("real-continuous-ui-flow", ["xcodebuild", "test-without-building"], timeout=480,
                    check=False, stop_on_fixed_assertion=True)
            self.assertEqual(code, -15)
            self.assertEqual(kill.call_args.args[0], 65432)
            self.assertTrue(runner.facts[0]["stoppedEarlyAfterObservedAssertion"])
            self.assertFalse(runner.facts[0]["timedOut"])
            self.assertEqual(runner.facts[0]["observedFixedXCTestAssertions"], ["FROZEN_VISIBLE_CONTROL_MISSING_gameCanvas"])
            self.assertEqual([call.kwargs["timeout"] for call in process.wait.call_args_list], [1.0, 10, 10])

    def test_source_literal_or_unrelated_error_cannot_trigger_early_stop(self):
        self.assertEqual(driver.observed_runtime_assertions(b'XCTFail("FROZEN_VISIBLE_CONTROL_MISSING_gameCanvas")\n'), [])
        self.assertEqual(driver.observed_runtime_assertions(b"error: some unrelated non-fixed failure\n"), [])
        self.assertEqual(driver.observed_runtime_assertions(b"error: XCTAssertTrue failed - FROZEN_NATIVE_PLAYING_WEBVIEW_FRAME_UNVERIFIED\n"),
            ["FROZEN_NATIVE_PLAYING_WEBVIEW_FRAME_UNVERIFIED"])

    def test_owned_recorder_finalizes_by_sigint_and_never_claims_killed_video_success(self):
        recorder = mock.Mock()
        recorder.poll.return_value = None
        recorder.wait.return_value = 0
        finalized, code, warning = driver.finish_owned_recording(recorder, True)
        self.assertTrue(finalized)
        self.assertEqual(code, 0)
        self.assertIsNone(warning)
        recorder.send_signal.assert_called_once_with(driver.signal.SIGINT)
        recorder.wait.side_effect = [subprocess.TimeoutExpired(["simctl"], 30), -15]
        finalized, code, warning = driver.finish_owned_recording(recorder, True)
        self.assertFalse(finalized)
        self.assertIsNotNone(warning)

    def test_timeout_terminates_only_own_process_group(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = driver.Commands(temporary)
            process = mock.Mock(pid=43210, returncode=-9)
            process.poll.return_value = None
            process.wait.side_effect = [subprocess.TimeoutExpired(["xcodebuild"], 5),
                subprocess.TimeoutExpired(["xcodebuild"], 10), -9]
            with mock.patch.object(driver.subprocess, "Popen", return_value=process), mock.patch.object(driver.os, "killpg", create=True) as kill, mock.patch.object(driver.signal, "SIGKILL", 9, create=True):
                with self.assertRaises(driver.CaptureFailure):
                    runner.run("bounded-test", ["xcodebuild", "build"], timeout=5)
            self.assertEqual([call.args[0] for call in kill.call_args_list], [43210, 43210])
            self.assertTrue(runner.facts[0]["timedOut"])
            self.assertEqual(runner.facts[0]["exitCode"], -9)
            self.assertEqual([call.kwargs["timeout"] for call in process.wait.call_args_list], [5, 10, 10])

    def test_host_interruption_cleans_the_owned_running_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = driver.Commands(temporary)
            process = mock.Mock(pid=54321, returncode=-15)
            process.poll.return_value = None
            process.wait.side_effect = [driver.CaptureFailure("Recording interrupted by host signal"), -15]
            with mock.patch.object(driver.subprocess, "Popen", return_value=process), mock.patch.object(driver.os, "killpg", create=True) as kill:
                with self.assertRaisesRegex(driver.CaptureFailure, "host signal"):
                    runner.run("bounded-test", ["xcodebuild", "build"], timeout=5)
            self.assertEqual(kill.call_args.args[0], 54321)
            self.assertEqual(runner.facts[0]["exitCode"], -15)

    def test_invalid_timeout_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(driver.subprocess, "Popen") as launch:
            runner = driver.Commands(temporary)
            with self.assertRaises(driver.CaptureFailure):
                runner.run("invalid", ["xcodebuild"], timeout=0)
            launch.assert_not_called()

    def test_original_recorder_stops_before_xcresult_queries(self):
        text = pathlib.Path(driver.__file__).read_text(encoding="utf-8")
        after_test = text.index('test_raw, test_exit = commands.run("real-continuous-ui-flow"')
        finish = text.index("finish_owned_recording(recorder, recorder_started)", after_test)
        self.assertLess(finish, text.index('commands.run("xcresult-summary"', after_test))


class NativeFailureDiagnosticsTests(unittest.TestCase):
    def test_fixed_test_stages_and_progress_discard_untrusted_log_content(self):
        stage = {"stage": "before-proxy", "utcUnixSeconds": 1791742605.0}
        raw = ("ASHES_TEST_STAGE_JSON=" + json.dumps(stage) + "\n"
               "Test Suite 'All tests' started at private-clock-data\n"
               "Test Case '-[AshesCaptureUITests.AshesCaptureUITests testContinuousLaunchSortieAndReturn]' started.\n"
               "Testing started\n"
               "Test Case '-[UnrelatedTests publishSecret]' passed (1.0 seconds).\n"
               "Command line invocation: /Users/private-owner password=DO-NOT-PUBLISH\n").encode()
        result = driver.safe_xctest_progress(raw)
        self.assertEqual(result["stageRecords"], [stage])
        self.assertEqual(result["lastObservedStage"], "before-proxy")
        self.assertEqual(result["fixedProgress"], ["suite:All tests:started", "own-testcase:started", "testing-started"])
        self.assertEqual(result["privateLogSha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["privateLogBytes"], len(raw))
        for secret in ("private-clock", "private-owner", "DO-NOT-PUBLISH", "publishSecret", "Command line"):
            self.assertNotIn(secret, json.dumps(result))
        self.assertFalse(result["absentMarkerProvesMethodNotEntered"])
        self.assertFalse(result["rootCauseConfirmed"])

    def test_stage_diagnostic_rejects_invalid_payloads_and_is_bounded(self):
        invalid = [{"stage": "secret-path", "utcUnixSeconds": 1791742605},
                   {"stage": "method-entry", "utcUnixSeconds": True},
                   {"stage": "method-entry", "utcUnixSeconds": float("nan")},
                   {"stage": "method-entry", "utcUnixSeconds": 1791742605, "extra": "private"},
                   {"stage": ["method-entry"], "utcUnixSeconds": 1791742605}]
        raw = ("\n".join("ASHES_TEST_STAGE_JSON=" + json.dumps(x) for x in invalid) + "\n").encode()
        self.assertEqual(driver.safe_xctest_progress(raw)["stageRecords"], [])
        valid = {"stage": "method-entry", "utcUnixSeconds": 1791742605}
        raw += (("ASHES_TEST_STAGE_JSON=" + json.dumps(valid) + "\nTesting started\n") * 40).encode()
        result = driver.safe_xctest_progress(raw)
        self.assertEqual(len(result["stageRecords"]), 12)
        self.assertEqual(len(result["fixedProgress"]), 12)
        self.assertFalse(driver.safe_xctest_progress(b"")["absentMarkerProvesMethodNotEntered"])
        self.assertIsNone(driver.safe_xctest_progress(b"")["lastObservedStage"])

    def test_method_diagnostics_bracket_existing_operations_without_actions(self):
        source = generator.SWIFT_TEST
        method = source.split("@MainActor func testContinuousLaunchSortieAndReturn() throws {", 1)[1]
        self.assertLess(method.index('diagnosticStage("method-entry")'), method.index("XCUIDevice.shared.orientation"))
        for before, operation, after in (("before-orientation", "XCUIDevice.shared.orientation = .portrait", "after-orientation"),
                ("before-proxy", "let app = XCUIApplication(bundleIdentifier: bundle)", "after-proxy"),
                ("before-state", "let beforeActivation = app.state", "after-state"),
                ("before-activate", "app.activate()", "after-activate")):
            self.assertLess(method.index('diagnosticStage("' + before + '")'), method.index(operation))
            self.assertLess(method.index(operation), method.index('diagnosticStage("' + after + '")'))
        diagnostic = source.split("private func diagnosticStage", 1)[1].split("private func event", 1)[0]
        self.assertIn("FileHandle.standardError.write(output)", diagnostic)
        self.assertNotIn("ordinal", diagnostic)
        self.assertNotIn("ASHES_ACTION_JSON", diagnostic)
        text = pathlib.Path(driver.__file__).read_text(encoding="utf-8")
        self.assertIn('self.facts[-1]["safeXCTestProgress"]', text)
        self.assertIn('self.facts[-1]["safeSummaryError"]', text)
        self.assertIn('"test-without-building"], 480', text)

    def test_frozen_prepare_and_record_use_explicit_263_known_baseline(self):
        workflow = pathlib.Path(__file__).parent.parent / ".github/workflows/web-runtime-probe.yml"
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("runs-on: macos-26-intel", text)
        job = text.split("  record:\n", 1)[1]
        self.assertIn("DEVELOPER_DIR: /Applications/Xcode_26.3.app/Contents/Developer", job.split("    steps:", 1)[0])
        prepare = job.split("      - name: Prepare frozen native source", 1)[1].split("      - name: Record a continuous", 1)[0]
        self.assertIn('bash "$CI_TOOLS/ci_ios_export.sh" prepare', prepare)
        self.assertNotIn("Xcode_26.6", prepare)
        recording = job.split("      - name: Record a continuous", 1)[1].split("      - uses:", 1)[0]
        self.assertIn("DEVELOPER_DIR: /Applications/Xcode_26.3.app/Contents/Developer", recording)
        source = pathlib.Path(driver.__file__).read_text(encoding="utf-8")
        self.assertIn('rb"^Xcode 26\\.3\\s*$"', source)
        self.assertNotIn('rb"^Xcode 26\\.6\\s*$"', source)

    def test_project_schema_read_precedes_expensive_native_operations(self):
        text = pathlib.Path(driver.__file__).read_text(encoding="utf-8")
        schema = text.index('commands.run("ui-project-schema"')
        for stage in ("inventory-before", "create-owned-simulator", "unsigned-game-build", "boot-owned-simulator", "install-frozen-app"):
            self.assertLess(schema, text.index('commands.run("' + stage + '"'))

    def test_error_excerpt_redacts_paths_urls_and_secrets(self):
        raw = ("Command line invocation: do-not-publish-this\n"
               "xcodebuild: error: Unable to read project /Users/private-owner/owned/AshesCapture.xcodeproj\n"
               "Reason: Could not read file from https://user:private-password@example.test/file\n"
               "xcodebuild: error: authorization Bearer DO-NOT-PUBLISH-KEY\n"
               "xcodebuild: error: token=DO-NOT-PUBLISH-TOKEN\n"
               "xcodebuild: error: cannot read AuthKey_DO-NOT-PUBLISH-ID.p8\n").encode()
        result = driver.safe_xcode_diagnostics(raw)
        output = json.dumps(result)
        for secret in ("private-owner", "private-password", "DO-NOT-PUBLISH", "Command line invocation"):
            self.assertNotIn(secret, output)
        self.assertFalse(result["rootCauseConfirmed"])
        self.assertTrue(result["rawCommandAndOutputWithheld"])
        self.assertIn("Unable to read project", output)

    def test_excerpt_is_bounded_and_does_not_publish_source_or_commands(self):
        raw = (("xcodebuild: error: " + "a" * 1000 + "\n") * 30
               + "let sourceBody = doNotPublish()\nCommand line invocation: xcodebuild ...\n").encode()
        result = driver.safe_xcode_diagnostics(raw)
        self.assertLessEqual(len(result["messages"]), 12)
        self.assertTrue(all(len(item) <= 512 for item in result["messages"]))
        self.assertNotIn("sourceBody", json.dumps(result))
        self.assertNotIn("Command line invocation", json.dumps(result))

    def test_project_list_requires_actual_fixed_scheme_and_targets(self):
        data = {"project": {"name": "AshesCapture", "targets": ["AshesCaptureHost", "AshesCaptureUITests"], "schemes": ["AshesCapture"]}}
        self.assertTrue(driver.project_schema_facts(json.dumps(data).encode())["projectSchemaReadByXcode"])
        data["project"]["schemes"] = []
        with self.assertRaises(driver.CaptureFailure):
            driver.project_schema_facts(json.dumps(data).encode())

    def test_actual_ui_build_binds_unsigned_simulator_sdk_and_owned_destination(self):
        device = {"udid": UDID, "name": driver.OWNER_PREFIX + "test-token"}
        args = driver.ui_xcode_args(pathlib.Path("generated"), pathlib.Path("derived"), device)
        self.assertEqual(args[args.index("-sdk") + 1], "iphonesimulator")
        self.assertEqual(args[args.index("-destination") + 1], "platform=iOS Simulator,id=" + UDID)
        self.assertIn("CODE_SIGNING_ALLOWED=NO", args)
        self.assertIn("CODE_SIGNING_REQUIRED=NO", args)
        for invalid in ({"udid": "all", "name": device["name"]}, {"udid": "booted", "name": device["name"]},
                        {"udid": UDID, "name": "Unrelated user device"}):
            with self.assertRaises(driver.CaptureFailure):
                driver.ui_xcode_args(pathlib.Path("generated"), pathlib.Path("derived"), invalid)

    def test_real_test_build_precedes_game_build_and_no_default_action_queries_remain(self):
        text = pathlib.Path(driver.__file__).read_text(encoding="utf-8")
        ui = text.index('commands.run("unsigned-ui-test-build"')
        self.assertIn('"build-for-testing"], 900)', text)
        self.assertLess(text.index('device = fresh_device('), ui)
        for stage in ("unsigned-game-build", "boot-owned-simulator", "install-frozen-app"):
            self.assertLess(ui, text.index('commands.run("' + stage + '"'))
        self.assertNotIn('"-showBuildSettings"', text)
        self.assertNotIn('"-showdestinations"', text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
