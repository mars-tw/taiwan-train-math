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
    def test_prefer_newest_available_compatible_runtime(self):
        data = inventory()
        data["runtimes"].extend([
            {"identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-3", "name": "iOS 26.3", "version": "26.3", "isAvailable": True},
            {"identifier": "com.apple.CoreSimulator.SimRuntime.iOS-27-0", "name": "iOS 27", "version": "27.0", "isAvailable": False}])
        self.assertEqual(driver.select_plan(data)["runtime"]["version"], "26.3")

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
        self.assertIn("app.launch()", swift)
        self.assertIn("element.tap()", swift)
        self.assertIn("thenDragTo: last", swift)
        for forbidden in ("evaluateJavaScript", "__test", "launchArguments", "launchEnvironment", "app.activate()", "setState("):
            self.assertNotIn(forbidden, swift)

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

    def encode(self, actions):
        return ("\n".join("ASHES_ACTION_JSON=" + json.dumps(item) for item in actions)).encode()

    def test_full_ordered_flow_accepted_and_partial_flow_rejected(self):
        self.assertEqual(len(driver.parse_actions(self.encode(self.actions), self.contract)), 16)
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


class NativeFailureDiagnosticsTests(unittest.TestCase):
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

    def test_settings_preserve_only_fixed_target_platform_and_sdk_facts(self):
        data = [{"target": target, "buildSettings": {"PLATFORM_NAME": "iphonesimulator", "SUPPORTED_PLATFORMS": "iphonesimulator",
                 "CODE_SIGNING_ALLOWED": "NO", "CODE_SIGNING_REQUIRED": "NO", "SDKROOT": "/Applications/Private/Xcode/iPhoneSimulator26.2.sdk",
                 "UNRELATED_PRIVATE_SETTING": "DO-NOT-PUBLISH"}} for target in ("AshesCaptureHost", "AshesCaptureUITests")]
        result = driver.ui_build_settings_facts(json.dumps(data).encode())
        self.assertNotIn("Private", json.dumps(result))
        self.assertNotIn("DO-NOT-PUBLISH", json.dumps(result))
        data[0]["buildSettings"]["CODE_SIGNING_ALLOWED"] = "YES"
        with self.assertRaises(driver.CaptureFailure):
            driver.ui_build_settings_facts(json.dumps(data).encode())

    def test_destination_must_be_owned_and_eligible_without_listing_other_devices(self):
        raw = ("Available destinations for the scheme:\n{ platform:iOS Simulator, id:" + UDID + ", name:Owned }\n"
               "Ineligible destinations for the scheme:\n{ platform:iOS Simulator, id:" + OTHER_UDID + ", name:OtherPersonPhone }\n").encode()
        result = driver.destination_facts(raw, UDID)
        self.assertTrue(result["ownedSimulatorEligible"])
        self.assertNotIn("OtherPersonPhone", json.dumps(result))
        self.assertNotIn(OTHER_UDID, json.dumps(result))
        with self.assertRaises(driver.CaptureFailure):
            driver.destination_facts(raw, OTHER_UDID)


if __name__ == "__main__":
    unittest.main(verbosity=2)
