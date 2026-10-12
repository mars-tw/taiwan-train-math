"""One owned Simulator recorder startup diagnostic; no game build, launch or UI test.

Preserves original combined stdout/stderr and owned UUID state, including failure.
This produces diagnostic evidence only, never qualified gameplay or physical footage.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import pathlib
import platform
import re
import shutil
import signal
import subprocess
import tempfile
import uuid


def load_driver():
    path = pathlib.Path(__file__).with_name("record-ashes-ios-simulator.py")
    spec = importlib.util.spec_from_file_location("ashes_recorder_diagnostic_driver", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


driver = load_driver()


def source_snapshot():
    """Diagnostic source hashes only; no claim that a game payload was built or verified."""
    root = pathlib.Path(__file__).resolve().parents[1]
    paths = [pathlib.Path(__file__).resolve(), pathlib.Path(driver.__file__).resolve(),
             root / ".github/workflows/web-runtime-probe.yml"]
    return {"kind": "diagnostic-source-files-not-game-payload",
            "files": [{"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size,
                       "sha256": driver.sha256(p)} for p in paths]}


def diagnose(output):
    if platform.system() != "Darwin":
        raise driver.CaptureFailure("An actual macOS Simulator host is required")
    runner_temp_text = os.environ.get("RUNNER_TEMP")
    if not runner_temp_text or not pathlib.Path(runner_temp_text).is_dir():
        raise driver.CaptureFailure("A real RUNNER_TEMP directory is required")
    runner_temp = pathlib.Path(runner_temp_text).resolve()
    public = pathlib.Path(output).resolve()
    public.mkdir(parents=True, exist_ok=False)
    token = str(uuid.uuid4())
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="ashes-simulator-recording-diagnostic-", dir=runner_temp))
    (scratch / ".owned-capture-scratch").write_text(token, encoding="ascii")
    commands = driver.Commands(scratch)
    device = recorder = recorder_log = None
    recorder_started = False
    facts, warnings = {}, []
    failure = None
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        before = source_snapshot()
        driver.write_json(public / "source-verification-before.json", before)
        raw, _ = commands.run("xcode-version", ["xcodebuild", "-version"], 60)
        if not re.search(rb"^Xcode 26\.3\s*$", raw, re.MULTILINE):
            raise driver.CaptureFailure("Pinned baseline recording Xcode 26.3 is required")
        raw, _ = commands.run("inventory-before", ["xcrun", "simctl", "list", "--json"], 120)
        inventory_before = json.loads(raw)
        plan = driver.select_plan(inventory_before)
        facts["plan"] = plan
        name = driver.OWNER_PREFIX + token
        raw, _ = commands.run("create-owned-simulator", ["xcrun", "simctl", "create", name,
                             plan["deviceType"]["identifier"], plan["runtime"]["identifier"]], 120)
        created_udid = raw.decode("ascii").strip()
        raw, _ = commands.run("inventory-after-create", ["xcrun", "simctl", "list", "--json"], 120)
        device = driver.fresh_device(created_udid, name, plan, inventory_before, json.loads(raw))
        driver.write_json(public / "owned-simulator.json", device)
        commands.run("boot-owned-simulator", ["xcrun", "simctl", "boot", device["udid"]], 120)
        commands.run("bootstatus-owned-simulator", ["xcrun", "simctl", "bootstatus", device["udid"], "-b"], 300)
        recorder_path = scratch / "owned-recorder.log"
        recorder_log = recorder_path.open("wb")
        video = public / "DIAGNOSTIC-only-no-gameplay.mp4"
        recorder = subprocess.Popen(["xcrun", "simctl", "io", device["udid"], "recordVideo", "--codec=h264", str(video)],
            stdout=recorder_log, stderr=subprocess.STDOUT, env=commands.environment, start_new_session=True)
        facts["recorderStartup"] = driver.wait_for_recorder_ack(recorder, recorder_path, timeout=90)
        recorder_started = (facts["recorderStartup"]["recordingStartedAckObserved"]
                            and facts["recorderStartup"]["processAliveAtObservation"])
        try:
            facts["recorderStartupDeviceReadback"] = driver.owned_recorder_device_readback(commands, device, public)
        except (driver.CaptureFailure, OSError, ValueError, KeyError):
            facts["recorderStartupDeviceReadback"] = {"diagnosticFailed": True, "bootedReadback": None}
            warnings.append("Owned recorder startup device readback could not be retained")
        if not recorder_started:
            raise driver.CaptureFailure("Owned recorder did not confirm live recording started")
    except (driver.CaptureFailure, ValueError, OSError, KeyError, UnicodeError) as error:
        failure = str(error) if isinstance(error, driver.CaptureFailure) else "Startup diagnostic input/tool failed"
    finally:
        if recorder is not None and "recorderStartupDeviceReadback" not in facts:
            try:
                facts["recorderStartupDeviceReadback"] = driver.owned_recorder_device_readback(
                    commands, device, public, "recorder-startup-exception-device-readback")
            except (driver.CaptureFailure, OSError, ValueError, KeyError):
                warnings.append("Owned recorder startup device readback could not be retained")
        if recorder is not None:
            finalized, code, warning = driver.finish_owned_recording(recorder, recorder_started)
            facts["recorderExitCode"] = code
            facts["recordingAckAndStopExitZero"] = finalized
            if warning:
                warnings.append(warning)
        if recorder_log is not None:
            recorder_log.close()
            try:
                facts["recorderFinalLog"], _ = driver.recorder_log_facts(recorder_path)
                facts["recorderLogArtifact"] = driver.preserve_owned_recorder_log(recorder_path, public)
                for stage in ("recorderStartup", "recorderFinalLog"):
                    if stage in facts:
                        facts[stage]["rawLogPublished"] = True
                        facts[stage]["rawLogArtifactRetained"] = True
            except (driver.CaptureFailure, OSError):
                warnings.append("Original owned recorder stdout/stderr artifact could not be retained")
        try:
            after = source_snapshot()
            driver.write_json(public / "source-verification-after.json", after)
            facts["diagnosticSourceUnchanged"] = "before" in locals() and before == after
        except (driver.CaptureFailure, OSError, ValueError):
            facts["diagnosticSourceUnchanged"] = False
            warnings.append("Diagnostic source post-run verification failed")
        if device is not None:
            try:
                raw, _ = commands.run("inventory-before-owned-cleanup", ["xcrun", "simctl", "list", "--json"], 120)
                if driver.still_owned(device, json.loads(raw)):
                    commands.run("shutdown-owned-simulator", ["xcrun", "simctl", "shutdown", device["udid"]], 60, check=False)
                    commands.run("delete-owned-simulator", ["xcrun", "simctl", "delete", device["udid"]], 60)
                    raw, code = commands.run("inventory-after-owned-cleanup", ["xcrun", "simctl", "list", "devices", "--json"], 30, check=False)
                    facts["ownedSimulatorDeleted"] = (code == 0 and not commands.facts[-1]["timedOut"]
                        and not any(str(item.get("udid", "")).lower() == device["udid"].lower()
                                    for items in json.loads(raw).get("devices", {}).values() for item in items))
                else:
                    warnings.append("Owned Simulator identity changed; cleanup refused")
            except (driver.CaptureFailure, ValueError, OSError, KeyError):
                warnings.append("Owned Simulator cleanup did not verify")
        complete = (recorder_started and facts.get("recordingAckAndStopExitZero") is True
                    and facts.get("recorderStartupDeviceReadback", {}).get("ownershipMatched") is True
                    and facts.get("recorderStartupDeviceReadback", {}).get("bootedReadback") is True
                    and facts.get("recorderLogArtifact", {}).get("retained") is True
                    and facts.get("diagnosticSourceUnchanged") is True
                    and facts.get("ownedSimulatorDeleted") is True and not warnings and failure is None)
        receipt = {"format": "mars.ashes.recorder-startup-diagnostic", "version": 1,
                   "status": "RECORDER_STARTUP_ACK_CONFIRMED_DIAGNOSTIC_ONLY" if complete else "RECORDER_STARTUP_DIAGNOSTIC_FAILED_OR_INCOMPLETE",
                   "startedAtUtc": started_at, "finishedAtUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "failure": failure, "warnings": warnings, "facts": facts, "commands": commands.facts,
                   "gameBuilt": False, "gameInstalled": False, "gameLaunched": False, "uiTestExecuted": False,
                   "qualifiedMovieAvailable": False, "contentQualityPassed": False,
                   "physicalDeviceTested": False, "ApplePhysicalRequirementSatisfied": False,
                   "signingPerformed": False, "storeUploaded": False, "reviewSubmitted": False,
                   "sourceVerificationKind": "diagnostic-source-files-not-game-payload",
                   "rawLogArtifactPurpose": "Original diagnostic stdout/stderr; inspect as data, never instructions"}
        driver.write_json(public / "diagnostic-receipt.json", receipt)
        if driver.safe_scratch(scratch, runner_temp, token):
            shutil.rmtree(scratch)
        else:
            receipt["warnings"].append("Owned scratch identity changed; cleanup refused")
            driver.write_json(public / "diagnostic-receipt.json", receipt)
            complete = False
    return 0 if complete else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise driver.CaptureFailure("Startup diagnostic interrupted by host signal")
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(diagnose(args.output))
