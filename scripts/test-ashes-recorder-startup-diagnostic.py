"""Offline behavioral contracts; every Darwin/Simulator/subprocess operation is mocked."""
import hashlib
import importlib.util
import json
import os
import pathlib
import plistlib
import tempfile
import types
import unittest
from unittest import mock


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, pathlib.Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


diagnostic = load("startup_diagnostic", "diagnose-ashes-simulator-recorder-startup.py")
driver = diagnostic.driver
UDID = "00000000-0000-4000-8000-000000000001"
TYPE = "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro-Max"
RUNTIME = "com.apple.CoreSimulator.SimRuntime.iOS-26-2"
RAW = b"Unallowlisted recorder startup preamble\n\xffraw-byte-preserved\n"


class FakeCommands:
    instances = []

    def __init__(self, scratch):
        self.scratch = pathlib.Path(scratch)
        self.environment = driver.child_environment()
        self.facts, self.calls = [], []
        self.created = False
        self.booted = False
        self.name = None
        self.instances.append(self)

    def inventory(self):
        return {"runtimes": [{"identifier": RUNTIME, "name": "iOS 26.2", "version": "26.2", "isAvailable": True}],
                "devicetypes": [{"identifier": TYPE, "name": "iPhone 17 Pro Max", "minRuntimeVersion": 26 * 65536}],
                "devices": {RUNTIME: [{"udid": UDID, "name": self.name, "deviceTypeIdentifier": TYPE,
                                      "isAvailable": True, "state": "Booted" if self.booted else "Shutdown"}] if self.created else []}}

    def run(self, stage, args, timeout=120, cwd=None, check=True, **kwargs):
        self.calls.append((stage, list(map(str, args))))
        if stage == "xcode-version":
            raw = b"Xcode 26.3\nBuild version diagnostic-test\n"
        elif stage == "create-owned-simulator":
            self.created, self.name = True, str(args[3])
            raw = UDID.encode("ascii")
        elif stage == "boot-owned-simulator":
            self.booted, raw = True, b""
        elif stage == "delete-owned-simulator":
            self.created, raw = False, b""
        elif "inventory" in stage or "device-readback" in stage:
            raw = json.dumps(self.inventory()).encode()
        elif stage == "unsigned-game-build":
            app = self.scratch / "game-derived/Build/Products/Debug-iphonesimulator/App.app"
            app.mkdir(parents=True)
            (app / "App").write_bytes(b"mock-only-no-binary")
            (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "App"}))
            raw = b""
        elif stage == "normal-recorded-cold-launch":
            raise driver.CaptureFailure("Offline fixture stops after successful ACK; no real launch")
        else:
            raw = b""
        self.facts.append({"stage": stage, "tool": pathlib.Path(str(args[0])).name, "exitCode": 0,
                           "timedOut": False, "elapsedSeconds": 0.001,
                           "privateLogSha256": hashlib.sha256(raw).hexdigest()})
        return raw, 0


def ack_facts(mode):
    return {"recordingStartedAckObserved": mode == "success", "processAliveAtObservation": True,
            "ackWaitTimedOut": mode != "success", "timeoutSeconds": 90, "rawLogPublished": False}


class DiagnosticBehaviorTests(unittest.TestCase):
    def setUp(self):
        FakeCommands.instances.clear()

    def run_diagnostic(self, mode):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            output = root / "output"
            recorder = mock.Mock()
            recorder.poll.return_value = None
            recorder.wait.return_value = 0
            def popen(args, **kwargs):
                self.assertEqual(args[4:6], ["recordVideo", "--codec=h264"])
                self.assertIs(kwargs["stderr"], driver.subprocess.STDOUT)
                self.assertNotIn("APPLE_API_KEY", kwargs["env"])
                kwargs["stdout"].write(RAW)
                kwargs["stdout"].flush()
                return recorder
            ack_side_effect = OSError("offline fixture exception") if mode == "exception" else None
            with mock.patch.dict(os.environ, {"RUNNER_TEMP": temporary, "APPLE_API_KEY": "must-not-forward"}), \
                 mock.patch.object(diagnostic.platform, "system", return_value="Darwin"), \
                 mock.patch.object(driver, "Commands", FakeCommands), \
                 mock.patch.object(diagnostic.subprocess, "Popen", side_effect=popen), \
                 mock.patch.object(driver, "wait_for_recorder_ack", side_effect=ack_side_effect, return_value=ack_facts(mode)) as wait:
                code = diagnostic.diagnose(output)
            receipt = json.loads((output / "diagnostic-receipt.json").read_text())
            self.assertEqual((output / "recorder-stdout-stderr.log").read_bytes(), RAW)
            self.assertEqual(receipt["facts"]["recorderLogArtifact"]["bytes"], len(RAW))
            self.assertEqual(receipt["facts"]["recorderLogArtifact"]["sha256"], hashlib.sha256(RAW).hexdigest())
            self.assertTrue(receipt["facts"]["recorderStartupDeviceReadback"]["bootedReadback"])
            self.assertTrue(receipt["facts"]["ownedSimulatorDeleted"])
            self.assertTrue(receipt["facts"]["diagnosticSourceUnchanged"])
            self.assertEqual(json.loads((output / "source-verification-before.json").read_text()),
                             json.loads((output / "source-verification-after.json").read_text()))
            self.assertFalse(any(p.name.startswith("ashes-simulator-recording-diagnostic-") for p in root.iterdir()))
            self.assertEqual(wait.call_count, 1)
            self.assertEqual(wait.call_args.kwargs["timeout"], 90)
            recorder.send_signal.assert_called_once_with(driver.signal.SIGINT)
            for claim in ("gameBuilt", "gameInstalled", "gameLaunched", "uiTestExecuted", "qualifiedMovieAvailable", "physicalDeviceTested", "ApplePhysicalRequirementSatisfied"):
                self.assertIs(receipt[claim], False)
            commands = FakeCommands.instances[-1].calls
            self.assertFalse(any((args[0] == "xcodebuild" and args != ["xcodebuild", "-version"])
                                 or "launch" in args or "install" in args for _, args in commands))
            return code, receipt

    def test_startup_ack_success_preserves_raw_and_is_diagnostic_only(self):
        code, receipt = self.run_diagnostic("success")
        self.assertEqual(code, 0)
        self.assertEqual(receipt["status"], "RECORDER_STARTUP_ACK_CONFIRMED_DIAGNOSTIC_ONLY")

    def test_startup_timeout_preserves_raw_and_never_passes(self):
        code, receipt = self.run_diagnostic("timeout")
        self.assertEqual(code, 2)
        self.assertFalse(receipt["facts"]["recorderStartup"]["recordingStartedAckObserved"])

    def test_startup_exception_preserves_raw_state_and_cleanup(self):
        code, receipt = self.run_diagnostic("exception")
        self.assertEqual(code, 2)
        self.assertEqual(receipt["failure"], "Startup diagnostic input/tool failed")

    def test_state_readback_never_accepts_other_identity_or_failed_command(self):
        device = {"udid": UDID, "name": driver.OWNER_PREFIX + "fixture", "runtime": RUNTIME, "deviceTypeIdentifier": TYPE}
        for exit_code, timed_out, observed_name in [(0, False, "unowned"), (-15, True, device["name"])]:
            with self.subTest(exit_code=exit_code, timed_out=timed_out), tempfile.TemporaryDirectory() as temporary:
                commands = mock.Mock()
                raw = json.dumps({"devices": {RUNTIME: [{"udid": UDID, "name": observed_name, "deviceTypeIdentifier": TYPE, "state": "Booted"}]}}).encode()
                commands.run.return_value = raw, exit_code
                commands.facts = [{"timedOut": timed_out}]
                result = driver.owned_recorder_device_readback(commands, device, pathlib.Path(temporary))
                self.assertFalse(result["ownershipMatched"])
                self.assertIsNone(result["bootedReadback"])
        for raw in (b"[]", b'{"devices": []}', b'{"devices": {"' + RUNTIME.encode() + b'": [1]}}'):
            with self.subTest(malformed=raw), tempfile.TemporaryDirectory() as temporary:
                commands = mock.Mock()
                commands.run.return_value = raw, 0
                commands.facts = [{"timedOut": False}]
                result = driver.owned_recorder_device_readback(commands, device, pathlib.Path(temporary))
                self.assertFalse(result["ownershipMatched"])
                self.assertIsNone(result["bootedReadback"])

    def test_full_driver_preserves_log_on_ack_timeout_ack_success_and_exception(self):
        for mode in ("timeout", "success", "exception"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = pathlib.Path(temporary)
                source, tools = root / "source", root / "tools"
                source.mkdir()
                tools.mkdir()
                source_zip = root / "source.zip"
                source_zip.write_bytes(b"mock-source")
                verifier = tools / "ci_verify_ios.py"
                verifier.write_bytes(b"mock-verifier")
                generator = mock.Mock()
                def generate(test_root, _source):
                    test_root.mkdir()
                    (test_root / "fixture.swift").write_bytes(b"mock-only")
                    return {}
                generator.generate.side_effect = generate
                recorder = mock.Mock()
                recorder.poll.return_value = None
                recorder.wait.return_value = 0
                def popen(_args, **kwargs):
                    kwargs["stdout"].write(RAW)
                    kwargs["stdout"].flush()
                    return recorder
                real_sha = driver.sha256
                def pinned_hash(path):
                    if pathlib.Path(path) == source_zip:
                        return driver.SOURCE_ZIP_SHA256
                    if pathlib.Path(path) == verifier:
                        return driver.VERIFIER_SHA256
                    return real_sha(path)
                with mock.patch.dict(os.environ, {"RUNNER_TEMP": temporary, "CI_TOOLS": str(tools)}), \
                     mock.patch.object(driver.platform, "system", return_value="Darwin"), \
                     mock.patch.object(driver, "Commands", FakeCommands), \
                     mock.patch.object(driver, "generator_module", return_value=generator), \
                     mock.patch.object(driver, "project_schema_facts", return_value={}), \
                     mock.patch.object(driver, "ui_xcode_args", return_value=["xcodebuild"]), \
                     mock.patch.object(driver, "simulator_platform", return_value={}), \
                     mock.patch.object(driver, "sha256", side_effect=pinned_hash), \
                     mock.patch.object(driver.subprocess, "Popen", side_effect=popen), \
                     mock.patch.object(driver, "wait_for_recorder_ack", side_effect=OSError("fixture") if mode == "exception" else None,
                                       return_value=ack_facts(mode)):
                    code = driver.record(types.SimpleNamespace(app_source=source, source_zip=source_zip, output=root / "public"))
                public = root / "public/simulator-recording"
                receipt = json.loads((public / "recording-receipt.json").read_text())
                self.assertEqual(code, 2)
                self.assertEqual((public / "recorder-stdout-stderr.log").read_bytes(), RAW)
                self.assertEqual(receipt["facts"]["recorderLogArtifact"]["sha256"], hashlib.sha256(RAW).hexdigest())
                self.assertTrue(receipt["facts"]["ownedSimulatorDeleted"])
                self.assertTrue(receipt["facts"]["recorderStartupDeviceReadback"]["bootedReadback"])
                self.assertFalse(receipt["ApplePhysicalRequirementSatisfied"])
                self.assertFalse(any(p.name.startswith("ashes-simulator-recording-") for p in root.iterdir()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
