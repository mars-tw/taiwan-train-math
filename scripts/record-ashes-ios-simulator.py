"""Record one genuine, uninterrupted, unsigned Ashes Simulator UI flow.

The MP4 is the original simctl recording, never assembled from screenshots.
This builds the same frozen web/native payload for iphonesimulator; it is not
the submitted iphoneos IPA binary and never satisfies Apple's physical-device
recording request. No signing, keychain, upload or store operation is included.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import platform
import plistlib
import re
import shutil
import signal
import subprocess
import tempfile
import time
import uuid

SOURCE_ZIP_SHA256 = "1abd7f426e81dc5d15aa84a38d23e6b7672fa8f0da011e1dce4d750dce78efc4"
MANIFEST_SHA256 = "b778a8203bd0ff31b10baf5f63d92e3387ced346586dea2526c0254b2d7c8c53"
VERIFIER_SHA256 = "e5cd13cc6405ce290ebe539d317daa2c6d5fdc7c3a02f883547e1d9694e737ab"
APP_ID = "tw.mars.ashesconvoy"
OWNER_PREFIX = "Mars-Ashes-SIMULATOR-"
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
TYPE_RE = re.compile(r"^com\.apple\.CoreSimulator\.SimDeviceType\.[A-Za-z0-9.-]+$")
RUNTIME_RE = re.compile(r"^com\.apple\.CoreSimulator\.SimRuntime\.iOS-\d+(?:-\d+)*$")


class CaptureFailure(Exception):
    """Messages are fixed, non-secret stage descriptions, never tool stderr."""


def sha256(path):
    value = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path, data):
    pathlib.Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generator_module():
    file = pathlib.Path(__file__).with_name("create-ashes-simulator-capture-project.py")
    spec = importlib.util.spec_from_file_location("ashes_capture_generator", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def version_parts(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+){0,2}", value):
        raise CaptureFailure("Simulator runtime version is invalid")
    return tuple(int(part) for part in value.split("."))


def select_plan(inventory):
    runtimes = [item for item in inventory.get("runtimes", [])
                if item.get("isAvailable") is True and not item.get("availabilityError")
                and RUNTIME_RE.fullmatch(str(item.get("identifier", "")))
                and version_parts(item.get("version", ""))[0] >= 26]
    runtimes.sort(key=lambda item: version_parts(item["version"]), reverse=True)
    for runtime in runtimes:
        parts = (*version_parts(runtime["version"]), 0, 0)[:3]
        number = parts[0] * 65536 + parts[1] * 256 + parts[2]
        choices = [item for item in inventory.get("devicetypes", [])
                   if TYPE_RE.fullmatch(str(item.get("identifier", "")))
                   and re.fullmatch(r"iPhone \d+(?:[A-Za-z ]*) Pro Max", str(item.get("name", "")))
                   and type(item.get("minRuntimeVersion", 0)) is int
                   and type(item.get("maxRuntimeVersion", 0xFFFFFFFF)) is int
                   and item.get("minRuntimeVersion", 0) <= number <= item.get("maxRuntimeVersion", 0xFFFFFFFF)]
        choices.sort(key=lambda item: (item["name"] == "iPhone 17 Pro Max", int(re.search(r"\d+", item["name"])[0])), reverse=True)
        if choices:
            return {"runtime": {key: runtime[key] for key in ("identifier", "name", "version")},
                    "deviceType": {key: choices[0][key] for key in ("identifier", "name")},
                    "selection": "newest-available-compatible-iOS-at-least-26; prefer-iPhone-17-Pro-Max"}
    raise CaptureFailure("Available iOS 26+ runtime and compatible iPhone Pro Max are required")


def fresh_device(udid, name, plan, inventory_before, inventory_after):
    if not UUID_RE.fullmatch(udid) or not name.startswith(OWNER_PREFIX):
        raise CaptureFailure("New Simulator identity is invalid")
    old = {str(item.get("udid", "")).lower() for items in inventory_before.get("devices", {}).values() for item in items}
    if udid.lower() in old:
        raise CaptureFailure("simctl did not create a fresh Simulator")
    matches = [item for item in inventory_after.get("devices", {}).get(plan["runtime"]["identifier"], [])
               if str(item.get("udid", "")).lower() == udid.lower()
               and item.get("name") == name and item.get("deviceTypeIdentifier") == plan["deviceType"]["identifier"]
               and item.get("isAvailable") is True]
    if len(matches) != 1:
        raise CaptureFailure("Fresh Simulator ownership could not be verified")
    return {"udid": udid, "name": name, "runtime": plan["runtime"]["identifier"], "deviceTypeIdentifier": plan["deviceType"]["identifier"]}


def still_owned(device, inventory):
    if not device or not UUID_RE.fullmatch(device.get("udid", "")) or not device.get("name", "").startswith(OWNER_PREFIX):
        return False
    matches = [item for item in inventory.get("devices", {}).get(device["runtime"], [])
               if str(item.get("udid", "")).lower() == device["udid"].lower()
               and item.get("name") == device["name"] and item.get("deviceTypeIdentifier") == device["deviceTypeIdentifier"]]
    return len(matches) == 1


def safe_scratch(scratch, runner_temp, token):
    scratch, runner_temp = pathlib.Path(scratch).resolve(), pathlib.Path(runner_temp).resolve()
    marker = scratch / ".owned-capture-scratch"
    return (scratch != runner_temp and scratch.is_relative_to(runner_temp)
            and scratch.name.startswith("ashes-simulator-recording-") and not scratch.is_symlink()
            and marker.is_file() and not marker.is_symlink() and marker.read_text(encoding="ascii") == token)


def child_environment():
    # The job requires no credentials. Do not forward Apple/Google publisher
    # secrets to build/test/record commands even if a caller has injected them.
    allowed = {"PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL", "SHELL", "DEVELOPER_DIR", "RUNNER_TEMP", "CI"}
    return {key: value for key, value in os.environ.items() if key in allowed}


def safe_xcode_diagnostics(raw):
    """Retain bounded tool error messages, never the command/source/log body.

    This is instrumentation, not a diagnosis inferred from a sysexits number.
    Secret-like lines are wholly withheld; paths and URLs are always redacted.
    """
    messages, remaining = [], 0
    for original in raw.decode("utf-8", errors="replace").splitlines():
        line = "".join(char if char.isprintable() else " " for char in original).strip()
        match = re.match(r"^(?:xcodebuild:\s*)?(?:error|fatal error):\s*(.{1,2048})$", line, re.IGNORECASE)
        if match:
            text, remaining = match[1], 6
        elif remaining and line:
            # Xcode emits a short Reason/error-description block after the
            # fatal prefix. Do not retain ordinary build commands or source.
            if re.match(r"^(?:Command line invocation|Build settings from command line|User defaults from command line|\*\*|CompileSwift|SwiftCompile|Ld\s|cd\s|/)", line):
                remaining = 0
                continue
            if not re.match(r"^(?:Reason:|Error\b|Underlying error|Domain:|Code:|The project\b|This project\b|This workspace\b|"
                            r"Could not\b|Unable to\b|Cannot\b|Failed to\b|The operation\b|Details:|Recovery|Exception:)", line, re.IGNORECASE):
                remaining = 0
                continue
            text, remaining = line[:2048], remaining - 1
        else:
            remaining = 0
            continue
        if re.search(r"authorization|bearer\s|password|private.?key|secret|token\s*[:=]|-----BEGIN|gh[pousr]_|\.p8\b|\.p12\b|\.mobileprovision\b", text, re.IGNORECASE):
            text = "<sensitive-diagnostic-withheld>"
        else:
            text = re.sub(r"https?://[^\s\"']+", "<url-withheld>", text, flags=re.IGNORECASE)
            text = re.sub(r"(?<!\w)/(?:[^\s\"':]+/?)+", "<absolute-path-withheld>", text)
            text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<absolute-path-withheld>", text)
        if text not in messages:
            messages.append(text[:512])
        if len(messages) >= 12:
            break
    return {"messages": messages, "maximumMessages": 12, "maximumCharactersPerMessage": 512,
            "rawCommandAndOutputWithheld": True, "rootCauseConfirmed": False}


def project_schema_facts(raw):
    try:
        data = json.loads(raw)
        project = data["project"]
    except (ValueError, KeyError, TypeError):
        raise CaptureFailure("Generated project list did not produce the expected JSON schema") from None
    expected = {"AshesCaptureHost", "AshesCaptureUITests"}
    if project.get("name") != "AshesCapture" or set(project.get("targets", [])) != expected or "AshesCapture" not in project.get("schemes", []):
        raise CaptureFailure("Generated UI-test project/scheme/targets did not read back correctly")
    return {"project": "AshesCapture", "requiredSchemePresent": True, "targets": sorted(expected),
            "projectSchemaReadByXcode": True, "rawListJsonWithheld": True,
            "listJsonSha256": hashlib.sha256(raw).hexdigest()}


def ui_build_settings_facts(raw):
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        raise CaptureFailure("Generated UI build settings were not JSON") from None
    if not isinstance(data, list):
        raise CaptureFailure("Generated UI build settings schema is unexpected")
    targets = {}
    for item in data:
        if not isinstance(item, dict) or item.get("target") not in ("AshesCaptureHost", "AshesCaptureUITests"):
            continue
        settings = item.get("buildSettings", {})
        if not isinstance(settings, dict):
            raise CaptureFailure("Generated UI target build settings schema is unexpected")
        if (settings.get("PLATFORM_NAME") != "iphonesimulator"
                or settings.get("SUPPORTED_PLATFORMS", "").split() != ["iphonesimulator"]
                or settings.get("CODE_SIGNING_ALLOWED") != "NO" or settings.get("CODE_SIGNING_REQUIRED") != "NO"):
            raise CaptureFailure("Generated UI targets are not explicitly unsigned Simulator builds")
        sdk_name = pathlib.PurePosixPath(settings.get("SDKROOT", "")).name
        if not re.fullmatch(r"(?:iPhoneSimulator\d+(?:\.\d+)*\.sdk|iphonesimulator\d*(?:\.\d+)*)", sdk_name):
            raise CaptureFailure("Generated UI target SDK root is not a Simulator SDK")
        targets[item["target"]] = {"platform": "iphonesimulator", "supportedPlatforms": ["iphonesimulator"],
            "codeSigningAllowed": "NO", "codeSigningRequired": "NO", "sdkName": sdk_name}
    if set(targets) != {"AshesCaptureHost", "AshesCaptureUITests"}:
        raise CaptureFailure("Generated UI build settings did not include both independent targets")
    return {"targets": targets, "rawBuildSettingsJsonWithheld": True,
            "buildSettingsJsonSha256": hashlib.sha256(raw).hexdigest()}


def destination_facts(raw, owned_udid):
    if not UUID_RE.fullmatch(owned_udid):
        raise CaptureFailure("Destination check requires the owned Simulator UUID")
    text = raw.decode("utf-8", errors="replace")
    available = text.split("Available destinations for", 1)
    eligible = available[1].split("Ineligible destinations", 1)[0] if len(available) == 2 else ""
    matches = re.findall(r"\bid:\s*([0-9a-fA-F-]{36})\b", eligible)
    if owned_udid.lower() not in [item.lower() for item in matches]:
        raise CaptureFailure("Owned Simulator was not an eligible UI-test scheme destination")
    return {"ownedSimulatorEligible": True, "ownedSimulatorId": owned_udid, "rawDestinationListingWithheld": True,
            "destinationListingSha256": hashlib.sha256(raw).hexdigest()}


class Commands:
    def __init__(self, scratch):
        self.scratch = pathlib.Path(scratch)
        self.facts = []
        self.environment = child_environment()
        self.counter = 0

    def run(self, stage, args, timeout=120, cwd=None, check=True):
        if not re.fullmatch(r"[a-z0-9-]+", stage) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise CaptureFailure("Invalid bounded command contract")
        self.counter += 1
        log = self.scratch / (str(self.counter) + "-" + stage + ".log")
        start, code, timed_out = time.monotonic(), None, False
        interruption = None

        def stop_owned_command(process):
            if process is None or process.poll() is not None:
                return process.returncode if process else None
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                return process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return process.wait(timeout=10)

        with log.open("wb") as output:
            process = None
            try:
                process = subprocess.Popen(list(map(str, args)), stdout=output, stderr=subprocess.STDOUT,
                    cwd=cwd, env=self.environment, start_new_session=True)
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                # Only this owned command/process group; no killall/pkill.
                code = stop_owned_command(process)
            except CaptureFailure as error:
                interruption = error
                code = stop_owned_command(process)
            except OSError:
                code = None
        self.facts.append({"stage": stage, "tool": pathlib.Path(str(args[0])).name, "exitCode": code,
            "timedOut": timed_out, "elapsedSeconds": round(time.monotonic() - start, 3),
            "privateLogSha256": sha256(log), "rawCommandAndOutputWithheld": True})
        diagnostics = []
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.search(r"(AshesCaptureUITests\.swift|CaptureHost\.swift):(\d+):(\d+): error: (.{1,500})$", line)
            if match:
                diagnostics.append({"generatedFile": match[1], "line": int(match[2]), "column": int(match[3]),
                                    "diagnostic": re.sub(r"/[^\s\"']+", "<path-withheld>", match[4])})
        if diagnostics:
            self.facts[-1]["generatedSwiftCompilerErrors"] = diagnostics[:20]
        if pathlib.Path(str(args[0])).name == "xcodebuild" and (timed_out or code != 0):
            self.facts[-1]["safeXcodeDiagnostics"] = safe_xcode_diagnostics(log.read_bytes())
        if interruption:
            raise interruption
        if check and (timed_out or code != 0):
            raise CaptureFailure("Bounded command failed at " + stage)
        return log.read_bytes(), code


def parse_actions(raw, contract):
    decoder, actions = json.JSONDecoder(), []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        marker = "ASHES_ACTION_JSON="
        if marker not in line:
            continue
        try:
            item, length = decoder.raw_decode(line.split(marker, 1)[1])
        except (ValueError, TypeError):
            raise CaptureFailure("XCTest action JSON is invalid") from None
        if not isinstance(item, dict):
            raise CaptureFailure("XCTest action is not a record")
        actions.append(item)
    if [item.get("action") for item in actions] != list(contract["actionSequence"]):
        raise CaptureFailure("Required real UI flow did not complete exactly once")
    last = -1
    for index, item in enumerate(actions, 1):
        elapsed = item.get("elapsedSeconds")
        if item.get("ordinal") != index or item.get("simulator") is not True or type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < last:
            raise CaptureFailure("Action order/timing/Simulator contract failed")
        last = elapsed
        if item["action"].endswith("-visible"):
            if item.get("foreground") is not True or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("screenshotSha256", ""))):
                raise CaptureFailure("Foreground screenshot checkpoint is missing")
        if "frozenControl" in item and contract["controls"].get(item["frozenControl"]) != item.get("label"):
            raise CaptureFailure("Action did not target the frozen visible label")
    return actions


def result_counts(raw):
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        raise CaptureFailure("xcresult summary is not JSON") from None
    facts = {key: data.get(key) for key in ("totalTestCount", "passedTests", "failedTests", "skippedTests")}
    if any(type(value) is not int for value in facts.values()) or facts != {
            "totalTestCount": 1, "passedTests": 1, "failedTests": 0, "skippedTests": 0}:
        raise CaptureFailure("xcresult did not prove the one required UI test passed")
    facts["summarySha256"] = hashlib.sha256(raw).hexdigest()
    return facts


def simulator_platform(info, raw_vtool):
    if (info.get("CFBundleIdentifier"), info.get("CFBundleShortVersionString"), str(info.get("CFBundleVersion")),
            info.get("DTPlatformName"), info.get("CFBundleSupportedPlatforms")) != (
            APP_ID, "1.0.1", "2", "iphonesimulator", ["iPhoneSimulator"]):
        raise CaptureFailure("Built App is not the approved Simulator platform/version")
    text = raw_vtool.decode("utf-8", errors="replace")
    platforms = re.findall(r"^\s*platform\s+(\w+)\s*$", text, re.MULTILINE)
    if not platforms or any(value != "IOSSIMULATOR" for value in platforms):
        raise CaptureFailure("Main Mach-O Simulator platform is unverified")
    return {"infoPlatform": "iphonesimulator", "supportedPlatforms": ["iPhoneSimulator"],
            "mainMachOPlatforms": platforms, "mainMachOPlatformVerified": True,
            "sameFrozenPayloadAsDeviceRelease": True, "sameBinaryAsDeviceIPA": False}


AV_METADATA_SWIFT = r'''import Foundation
import AVFoundation
let asset = AVURLAsset(url: URL(fileURLWithPath: CommandLine.arguments[1]))
let tracks = asset.tracks(withMediaType: .video)
guard tracks.count == 1 else { exit(2) }
let duration = CMTimeGetSeconds(asset.duration)
let track = tracks[0]
let transformed = track.naturalSize.applying(track.preferredTransform)
guard duration.isFinite && duration > 0, abs(transformed.width) > 0, abs(transformed.height) > 0 else { exit(3) }
let metadata: [String:Any] = ["durationSeconds": duration, "width": abs(transformed.width), "height": abs(transformed.height),
    "nominalFrameRate": track.nominalFrameRate, "videoTrackCount": tracks.count,
    "audioTrackCount": asset.tracks(withMediaType: .audio).count, "contentQualityPassed": false]
let raw = try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys])
print(String(data: raw, encoding: .utf8)!)
'''


def metadata_facts(raw):
    try:
        data = json.loads(raw.decode("utf-8").splitlines()[-1])
    except (ValueError, TypeError, IndexError, UnicodeError):
        raise CaptureFailure("Original MP4 metadata could not be read") from None
    if (data.get("videoTrackCount") != 1 or type(data.get("durationSeconds")) not in (int, float)
            or not math.isfinite(data["durationSeconds"]) or data["durationSeconds"] < 15
            or any(type(data.get(key)) not in (int, float) or not math.isfinite(data[key]) or data[key] < 1 for key in ("width", "height"))
            or type(data.get("nominalFrameRate")) not in (int, float) or not math.isfinite(data["nominalFrameRate"]) or data["nominalFrameRate"] <= 0
            or type(data.get("audioTrackCount")) is not int or data["audioTrackCount"] < 0
            or data.get("contentQualityPassed") is not False):
        raise CaptureFailure("Original MP4 lacks required continuous video metadata")
    return data


def record(args):
    if platform.system() != "Darwin":
        raise CaptureFailure("An actual macOS Simulator host is required")
    source, source_zip = args.app_source.resolve(), args.source_zip.resolve()
    tools = pathlib.Path(os.environ.get("CI_TOOLS", "")).resolve()
    runner_temp_text = os.environ.get("RUNNER_TEMP")
    if not runner_temp_text or not pathlib.Path(runner_temp_text).is_dir():
        raise CaptureFailure("A real RUNNER_TEMP directory is required")
    runner_temp = pathlib.Path(runner_temp_text).resolve()
    verifier = tools / "ci_verify_ios.py"
    if not source.is_dir() or source_zip.is_symlink() or not source_zip.is_file() or sha256(source_zip) != SOURCE_ZIP_SHA256:
        raise CaptureFailure("Approved frozen source ZIP is missing or its pin differs")
    if not verifier.is_file() or verifier.is_symlink() or sha256(verifier) != VERIFIER_SHA256:
        raise CaptureFailure("Approved CI_TOOLS verifier pin differs")
    generator = generator_module()
    generator.inspect_source(source)
    public = args.output.resolve() / "simulator-recording"
    if public == source or public.is_relative_to(source) or source.is_relative_to(public):
        raise CaptureFailure("Recording output must be independent of source")
    public.mkdir(parents=True, exist_ok=False)
    token = str(uuid.uuid4())
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="ashes-simulator-recording-", dir=runner_temp))
    (scratch / ".owned-capture-scratch").write_text(token, encoding="ascii")
    commands = Commands(scratch)
    device, recorder, recorder_log = None, None, None
    recorder_started, recorder_finalized, capture_passed = False, False, False
    failed_stage, errors, facts, actions = None, [], {}, []
    video = public / "SIMULATOR-ashes-convoy-1.0.1-build2-continuous-original.mp4"
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        xcode, _ = commands.run("xcode-version", ["xcodebuild", "-version"], 60)
        if not re.search(rb"^Xcode 26\.3\s*$", xcode, re.MULTILINE):
            raise CaptureFailure("Pinned Xcode 26.3 is required")
        commands.run("verify-source-before", ["python3", verifier, "source", "--root", source, "--project", "ashes-convoy", "--output", public / "source-verification-before.json"])
        raw, _ = commands.run("inventory-before", ["xcrun", "simctl", "list", "--json"])
        before = json.loads(raw)
        plan = select_plan(before)
        facts["plan"] = plan
        name = OWNER_PREFIX + token
        raw, _ = commands.run("create-owned-simulator", ["xcrun", "simctl", "create", name, plan["deviceType"]["identifier"], plan["runtime"]["identifier"]])
        created_udid = raw.decode("ascii").strip()
        raw, _ = commands.run("inventory-after-create", ["xcrun", "simctl", "list", "--json"])
        device = fresh_device(created_udid, name, plan, before, json.loads(raw))
        write_json(public / "owned-simulator.json", device)
        derived = scratch / "game-derived"
        commands.run("unsigned-game-build", ["xcodebuild", "-project", source / "ios/App/App.xcodeproj", "-scheme", "App",
            "-configuration", "Debug", "-sdk", "iphonesimulator", "-destination", "generic/platform=iOS Simulator",
            "-derivedDataPath", derived, "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO", "ONLY_ACTIVE_ARCH=NO", "build"], 1800, source)
        app = derived / "Build/Products/Debug-iphonesimulator/App.app"
        commands.run("verify-simulator-app", ["python3", verifier, "app", "--root", source, "--project", "ashes-convoy", "--app", app, "--output", public / "simulator-app-verification.json"])
        info = plistlib.loads((app / "Info.plist").read_bytes())
        executable = info.get("CFBundleExecutable")
        if not isinstance(executable, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", executable):
            raise CaptureFailure("Simulator main executable identity is invalid")
        raw, _ = commands.run("main-macho-platform", ["xcrun", "vtool", "-show-build", app / executable])
        facts["platform"] = simulator_platform(info, raw)
        facts["simulatorMainExecutableSha256"] = sha256(app / executable)
        commands.run("boot-owned-simulator", ["xcrun", "simctl", "boot", device["udid"]])
        commands.run("bootstatus-owned-simulator", ["xcrun", "simctl", "bootstatus", device["udid"], "-b"], 300)
        commands.run("install-frozen-app", ["xcrun", "simctl", "install", device["udid"], app], 180)
        # Fixed, non-secret independent generated files are retained so a
        # native build failure is inspectable after private logs are cleaned.
        test_root = public / "generated-ui-test-project"
        contract = generator.generate(test_root, source)
        facts["generatedUIProject"] = {"relativeDirectory": "generated-ui-test-project", "gameSourceIncluded": False,
            "files": [{"path": item.relative_to(test_root).as_posix(), "sha256": sha256(item), "bytes": item.stat().st_size}
                      for item in sorted(test_root.rglob("*")) if item.is_file()]}
        write_json(public / "capture-contract.json", contract)
        runner_derived = scratch / "test-derived"
        xcode_args = ["xcodebuild", "-project", test_root / "AshesCapture.xcodeproj", "-scheme", "AshesCapture",
            "-configuration", "Debug", "-sdk", "iphonesimulator", "-destination", "platform=iOS Simulator,id=" + device["udid"],
            "-derivedDataPath", runner_derived, "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO"]
        facts["uiRunnerPreflight"] = {}
        raw, _ = commands.run("ui-project-schema", ["xcodebuild", "-list", "-json", "-project", test_root / "AshesCapture.xcodeproj"], 120)
        facts["uiRunnerPreflight"]["schema"] = project_schema_facts(raw)
        raw, _ = commands.run("ui-build-settings", [*xcode_args, "-showBuildSettings", "-json"], 180)
        facts["uiRunnerPreflight"]["settings"] = ui_build_settings_facts(raw)
        raw, _ = commands.run("ui-destination-eligibility", ["xcodebuild", "-project", test_root / "AshesCapture.xcodeproj", "-scheme", "AshesCapture", "-showdestinations"], 120)
        facts["uiRunnerPreflight"]["destination"] = destination_facts(raw, device["udid"])
        commands.run("unsigned-ui-test-build", [*xcode_args, "-resultBundlePath", public / "ui-test-build.xcresult", "build-for-testing"], 900)
        recorder_path = scratch / "owned-recorder.log"
        recorder_log = recorder_path.open("wb")
        recorder = subprocess.Popen(["xcrun", "simctl", "io", device["udid"], "recordVideo", "--codec=h264", str(video)],
            stdout=recorder_log, stderr=subprocess.STDOUT, env=commands.environment, start_new_session=True)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if recorder.poll() is not None:
                raise CaptureFailure("Owned simctl recorder exited before launch")
            if b"Recording started" in recorder_path.read_bytes():
                recorder_started = True
                break
            time.sleep(0.25)
        if not recorder_started:
            raise CaptureFailure("Owned recorder did not confirm recording started")
        # Recording starts before normal app.launch() in the test. No restarting,
        # trimming, concatenating, screenshot-video creation or render injection.
        test_raw, test_exit = commands.run("real-continuous-ui-flow", [*xcode_args,
            "-resultBundlePath", public / "capture.xcresult", "-parallel-testing-enabled", "NO",
            "-maximum-concurrent-test-simulator-destinations", "1", "-test-timeouts-enabled", "YES",
            "-default-test-execution-time-allowance", "180", "-maximum-test-execution-time-allowance", "240",
            "-only-testing:AshesCaptureUITests/AshesCaptureUITests/testContinuousLaunchSortieAndReturn", "test-without-building"], 480, check=False)
        # Keep real partial action evidence on failure. Never turn it into a pass.
        partial = []
        for line in test_raw.decode("utf-8", errors="replace").splitlines():
            if "ASHES_ACTION_JSON=" in line:
                try:
                    item, _ = json.JSONDecoder().raw_decode(line.split("ASHES_ACTION_JSON=", 1)[1])
                    if isinstance(item, dict):
                        partial.append(item)
                except ValueError:
                    pass
        write_json(public / "observed-actions.json", partial)
        facts["fixedXCTestFailureAssertions"] = sorted(set(re.findall(
            r"FROZEN_VISIBLE_CONTROL_MISSING_[A-Za-z]+|FROZEN_APP_NOT_FOREGROUND|PAUSED_BEFORE_GAMEPLAY|"
            r"RESUME_PANEL_STILL_VISIBLE|SETTLEMENT_DID_NOT_REPLACE_PAUSE|SETTLEMENT_STILL_VISIBLE_AFTER_RETURN|"
            r"INPUT_START_OUTSIDE_VISIBLE_CONTROL|INPUT_END_OUTSIDE_VISIBLE_CONTROL",
            test_raw.decode("utf-8", errors="replace"))))
        summary_raw, summary_exit = commands.run("xcresult-summary", ["xcrun", "xcresulttool", "get", "test-results", "summary", "--path", public / "capture.xcresult"], 120, check=False)
        if summary_exit == 0:
            # Failure summaries only retain fixed counts; detailed attachments
            # remain in the original xcresult for independent inspection.
            try:
                summary = json.loads(summary_raw)
                facts["observedTestCounts"] = {key: summary.get(key) for key in ("totalTestCount", "passedTests", "failedTests", "skippedTests")}
                facts["xcresultSummarySha256"] = hashlib.sha256(summary_raw).hexdigest()
            except ValueError:
                pass
        if test_exit != 0:
            raise CaptureFailure("Real UI flow xcodebuild failed; partial action evidence retained")
        if summary_exit != 0:
            raise CaptureFailure("xcresult summary command failed")
        facts["tests"] = result_counts(summary_raw)
        actions = parse_actions(test_raw, contract)
        write_json(public / "verified-actions.json", actions)
        capture_passed = True
    except (CaptureFailure, ValueError, OSError, KeyError, UnicodeError) as error:
        failed_stage = str(error) if isinstance(error, CaptureFailure) else "Input/tool artifact could not meet the recording contract"
    finally:
        facts["uiTestBuildResultBundlePresent"] = (public / "ui-test-build.xcresult").is_dir()
        # Finalize only the exact recorder Popen handle owned by this invocation.
        if recorder is not None:
            try:
                if recorder.poll() is None:
                    recorder.send_signal(signal.SIGINT)
                code = recorder.wait(timeout=30)
                recorder_finalized = recorder_started and code == 0
                facts["recorderExitCode"] = code
            except (OSError, subprocess.TimeoutExpired):
                errors.append("Owned recorder did not finalize after SIGINT")
                try:
                    recorder.terminate()
                    recorder.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    recorder.kill()
                    recorder.wait(timeout=10)
        if recorder_log is not None:
            recorder_log.close()
        if recorder_finalized and video.is_file() and video.stat().st_size > 0:
            try:
                metadata = scratch / "inspect-original-mp4.swift"
                metadata.write_text(AV_METADATA_SWIFT, encoding="utf-8")
                raw, _ = commands.run("original-mp4-metadata", ["xcrun", "swift", metadata, video], 120)
                facts["video"] = {"file": video.name, "bytes": video.stat().st_size, "sha256": sha256(video),
                    "metadata": metadata_facts(raw), "originalUneditedSimctlRecording": True,
                    "fullRequiredUIFlowVerified": capture_passed, "audioCaptureVerified": False,
                    "contentQualityPassed": False, "localContentReviewRequired": True}
            except (CaptureFailure, OSError):
                errors.append("Finalized original MP4 metadata verification failed")
        else:
            errors.append("Original MP4 was not successfully finalized")
        try:
            commands.run("verify-source-after", ["python3", verifier, "source", "--root", source, "--project", "ashes-convoy", "--output", public / "source-verification-after.json"])
            generator.inspect_source(source)
            facts["frozenSourceVerifiedAfterCapture"] = True
        except (CaptureFailure, ValueError, OSError):
            facts["frozenSourceVerifiedAfterCapture"] = False
            errors.append("Frozen source post-capture verification failed")
        if device is not None:
            try:
                raw, _ = commands.run("inventory-before-owned-cleanup", ["xcrun", "simctl", "list", "--json"])
                if still_owned(device, json.loads(raw)):
                    commands.run("shutdown-owned-simulator", ["xcrun", "simctl", "shutdown", device["udid"]], 60, check=False)
                    commands.run("delete-owned-simulator", ["xcrun", "simctl", "delete", device["udid"]], 60)
                    facts["ownedSimulatorDeleted"] = True
                else:
                    errors.append("Owned Simulator identity changed; cleanup refused")
            except (CaptureFailure, ValueError, OSError):
                errors.append("Owned Simulator cleanup did not verify")
        valid = capture_passed and recorder_finalized and "video" in facts and facts.get("frozenSourceVerifiedAfterCapture") is True and not errors
        receipt = {"format": "mars.ashes.simulator-continuous-recording", "version": 1,
            "status": "SIMULATOR_FLOW_RECORDED_CONTENT_REVIEW_REQUIRED" if valid else "SIMULATOR_RECORDING_FAILED_OR_INCOMPLETE",
            "startedAtUtc": started_at, "finishedAtUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "projectId": "ashes-convoy", "appId": APP_ID, "appVersion": "1.0.1", "build": 2,
            "sourceZipSha256": SOURCE_ZIP_SHA256, "manifestSha256": MANIFEST_SHA256, "ciVerifierSha256": VERIFIER_SHA256,
            "simulatorCaptured": "video" in facts, "realUIFlowVerified": capture_passed,
            "physicalDeviceTested": False, "ApplePhysicalRequirementSatisfied": False,
            "sameFrozenPayloadAsDeviceRelease": True, "sameBinaryAsDeviceIPA": False,
            "contentQualityPassed": False, "localContentReviewRequired": True,
            "signingPerformed": False, "keychainModified": False, "storeUploaded": False, "reviewSubmitted": False,
            "failure": failed_stage, "warnings": errors, "facts": facts, "commands": commands.facts}
        write_json(public / "recording-receipt.json", receipt)
        if safe_scratch(scratch, runner_temp, token):
            shutil.rmtree(scratch)
        else:
            receipt["warnings"].append("Owned scratch identity changed; cleanup refused")
            write_json(public / "recording-receipt.json", receipt)
            valid = False
    return 0 if valid else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-source", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--source-zip", required=True, type=pathlib.Path)
    arguments = parser.parse_args()
    def interrupted(signum, frame):
        raise CaptureFailure("Recording interrupted by host signal")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        raise SystemExit(record(arguments))
    except CaptureFailure as failure:
        print("Unsigned Simulator recording unavailable: " + str(failure))
        raise SystemExit(2) from None
    except (OSError, ValueError, KeyError, TypeError):
        print("Unsigned Simulator recording unavailable: input/artifact contract failed")
        raise SystemExit(2) from None
