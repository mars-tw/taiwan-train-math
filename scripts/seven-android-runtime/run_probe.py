"""One exact Seven8 Android KVM observation through normal adb UI input only.

No app source, pack, save, mission or object state is edited. Captured control
flow is separate from root visual gameplay acceptance and first-chapter completion.
"""
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
import xml.etree.ElementTree as ET

from PIL import Image, ImageChops
import cv2
from fetch_input import fixed_input_pins
import numpy as np

PACKAGE = "tw.mars.sevendistrictreckoning"
ALIAS = PACKAGE + "/com.godot.game.GodotAppLauncher"
APK_NAME = "seven-district-reckoning-1.0.0-build8.apk"
CERT_SHA = "1dd3cc96a02e4555e8d91a42d749a019ee5c4781d4d7510947ae48c865e21110"
SERIAL = "emulator-5580"
GPU_MODE = "swangle"  # Explicit supported compatibility experiment, never fallback.


def verify_swangle_gpu_help(stdout, stderr, exit_code):
    if exit_code != 0 or not re.search(r"(?<![\w])swangle(?![\w])", stdout + stderr):
        raise RuntimeError("Pinned official emulator does not advertise swangle; no fallback")
    return True


def verify_swangle_boot_selection(log):
    if not re.search(r"gles_mode_selected:swangle\b", log):
        raise RuntimeError("Actual owned GLES mode is not explicit swangle target; no fallback")
    return True


def bounded_native_ocr(argv, remaining_seconds, runner=subprocess.run):
    """One OCR child with isolated OMP1 env and no extension to the900s flow."""
    env = os.environ.copy()
    env["OMP_THREAD_LIMIT"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    budget = min(60.0, remaining_seconds)
    if budget <= 0:
        raise RuntimeError("Absolute native observation deadline exceeded before OCR")
    started = time.monotonic()
    try:
        result = runner(argv, capture_output=True, timeout=budget, env=env)
        stdout, stderr, exit_code, timed_out = result.stdout or b"", result.stderr or b"", result.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout, stderr, exit_code, timed_out = error.stdout or b"", error.stderr or b"", None, True
    if isinstance(stdout, str):
        stdout = stdout.encode("utf-8")
    if isinstance(stderr, str):
        stderr = stderr.encode("utf-8")
    receipt = {"configuredMaximumSeconds":60, "effectiveBudgetSeconds":budget,
        "elapsedSeconds":round(time.monotonic()-started,6), "exitCode":exit_code,"timedOut":timed_out,
        "childOmpEnvironment":{"OMP_THREAD_LIMIT":"1","OMP_NUM_THREADS":"1"},
        "globalEnvironmentMutated":False,"flowDeadlineExtended":False,
        "stdoutBytes":len(stdout),"stderrBytes":len(stderr)}
    return stdout, stderr, receipt


def normalized(value):
    return re.sub(r"[^A-Za-z0-9\u3400-\u9fff]", "", value).casefold()


def label_box(tsv, caption):
    lines = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row.get("level") != "5" or not normalized(row.get("text", "")):
            continue
        try:
            if float(row["conf"]) < 25:
                continue
            key = tuple(row[k] for k in ["page_num", "block_num", "par_num", "line_num"])
            lines.setdefault(key, []).append(row)
        except (ValueError, KeyError):
            continue
    matches = []
    wanted = normalized(caption)
    for words in lines.values():
        words.sort(key=lambda word: int(word["left"]))
        text, spans = "", []
        for word in words:
            start = len(text)
            text += normalized(word["text"])
            spans.append((start, len(text), word))
        start = text.find(wanted)
        if start < 0 or text.find(wanted, start + 1) >= 0:
            continue
        contributing = [word for left, right, word in spans if right > start and left < start + len(wanted)]
        left = min(int(word["left"]) for word in contributing)
        top = min(int(word["top"]) for word in contributing)
        right = max(int(word["left"]) + int(word["width"]) for word in contributing)
        bottom = max(int(word["top"]) + int(word["height"]) for word in contributing)
        matches.append([left, top, right, bottom])
    if len(matches) > 1:
        raise RuntimeError("Ambiguous visible caption; no tap guessed")
    return matches[0] if matches else None


def system_ui_notice_box(xml, width, height):
    """Only the visible SystemUI fullscreen-education Got it caption can match."""
    if len(xml) > 512 * 1024 or "<!DOCTYPE" in xml or "<!ENTITY" in xml:
        raise RuntimeError("Unexpected native UI XML")
    tree = ET.fromstring(xml)
    matches = []
    for node in tree.iter("node"):
        if node.get("package") != "com.android.systemui" or node.get("text") != "Got it":
            continue
        if node.get("enabled", "true") != "true" or node.get("visible-to-user", "true") != "true":
            continue
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
        if not match:
            raise RuntimeError("SystemUI notice bounds invalid; no tap")
        left, top, right, bottom = map(int, match.groups())
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise RuntimeError("SystemUI notice outside original native frame; no tap")
        matches.append([left, top, right, bottom])
    if len(matches) > 1:
        raise RuntimeError("Ambiguous visible SystemUI Got it notices; no tap")
    return matches[0] if matches else None


def system_ui_notice_from_frame(xml, width, height, tsv, dismissals):
    """Exact SystemUI XML plus the observed education body, at most one tap."""
    if dismissals >= 1:
        return None
    title = label_box(tsv, "Viewing full screen")
    instruction = label_box(tsv, "To exit, swipe down from the top of your screen")
    if not title or not instruction:
        return None
    button = system_ui_notice_box(xml, width, height)
    if button is None:
        return None
    tree = ET.fromstring(xml)
    parents = {child: parent for parent in tree.iter() for child in parent}
    got_it = next(node for node in tree.iter("node")
                  if node.get("package") == "com.android.systemui" and node.get("text") == "Got it"
                  and node.get("enabled", "true") == "true" and node.get("visible-to-user", "true") == "true")
    panels = []
    parent = parents.get(got_it)
    while parent is not None:
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", parent.get("bounds", ""))
        if parent.get("package") == "com.android.systemui" and match:
            box = list(map(int, match.groups()))
            valid = 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height
            if valid and all(box[0] <= child[0] < child[2] <= box[2]
                             and box[1] <= child[1] < child[3] <= box[3]
                             for child in [title, instruction, button]):
                panels.append(box)
        parent = parents.get(parent)
    if not panels:
        return None
    panel = min(panels, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]))
    return {"buttonBounds": button, "panelBounds": panel,
            "titleOCRBounds": title, "instructionOCRBounds": instruction,
            "buttonOCRRequired": False, "ownerPackage": "com.android.systemui"}


def verify_avd_registry(ini, data, name, names, allowed_root):
    """Require actual official create output and emulator discovery before boot."""
    allowed_root = Path(allowed_root).resolve()
    ini, data = Path(ini), Path(data)
    if (ini.is_symlink() or data.is_symlink() or not ini.resolve().is_relative_to(allowed_root)
            or not data.resolve().is_relative_to(allowed_root)):
        raise RuntimeError("Owned AVD registry path/type leaves runner temp")
    if not ini.is_file() or not data.is_dir():
        raise RuntimeError("Official AVD registry/data missing; stop before boot")
    pairs = {}
    for line in ini.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key in pairs:
            raise RuntimeError("Duplicate official AVD registry property")
        pairs[key] = value
    if not pairs.get("path") or not Path(pairs["path"]).is_absolute() or Path(pairs["path"]).resolve() != data.resolve():
        raise RuntimeError("Official AVD registry points at wrong data path")
    if [line.strip() for line in names.splitlines() if line.strip()] != [name]:
        raise RuntimeError("Official emulator does not discover exactly the owned AVD")
    return {"registryPath": str(ini), "dataPath": str(data), "registryProperties": pairs,
            "emulatorListedNames": [name], "verified": True, "registryManuallyWritten": False}



def verify_phone720_wm_readback(text):
    physical = re.findall(r"^Physical size:\s*(\d+)x(\d+)\s*$", text, re.M)
    override = re.findall(r"^Override size:\s*(\d+)x(\d+)\s*$", text, re.M)
    if (len(physical) != 1 or len(override) != 1 or tuple(map(int, override[0])) != (720, 1280)
            or any(value <= 0 for value in map(int, physical[0]))
            or any(line.strip() and not re.fullmatch(r"(?:Physical|Override) size:\s*\d+x\d+\s*", line.strip()) for line in text.splitlines())):
        raise RuntimeError("Actual owned wm size readback is not unique720x1280 override; no launch")
    return {"physicalSize": list(map(int, physical[0])), "overrideNaturalPortraitSize": [720,1280],
            "expectedOriginalNativeLandscapePNG": [1280,720], "readbackVerified": True}


def verify_native_phone720_dimensions(width, height):
    if (width,height) != (1280,720):
        raise RuntimeError("Actual original native game PNG is not1280x720 landscape; no resize or coordinate guess")
    return True



def actual_uiautomator_xml(stdout, stderr, exit_code):
    """Raw cat diagnostics are not XML; never strip arbitrary text into proof."""
    if exit_code != 0:
        return None, "CAT_NONZERO_EXIT"
    if not isinstance(stdout, bytes) or not stdout or len(stdout) > 512 * 1024:
        return None, "EMPTY_OR_OVERSIZED_CAT_STDOUT"
    try:
        xml = stdout.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        return None, "CAT_STDOUT_NOT_UTF8_XML"
    if (not (xml.startswith("<?xml") or xml.startswith("<hierarchy"))
            or "<!DOCTYPE" in xml or "<!ENTITY" in xml):
        return None, "CAT_STDOUT_NOT_SAFE_XML"
    try:
        tree = ET.fromstring(xml)
    except ET.ParseError:
        return None, "CAT_STDOUT_MALFORMED_XML"
    if tree.tag != "hierarchy":
        return None, "CAT_XML_WRONG_ROOT"
    return xml, "VALID_ACTUAL_XML_PENDING_OWNED_NOTICE_FRAME_MATCH"


def main():
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != "mars-tw/taiwan-train-math"
            or os.environ.get("GITHUB_REF") != "refs/heads/codex/ashes-simulator-recording"):
        raise RuntimeError("Fixed Seven QA branch only")
    pins = fixed_input_pins()
    APK_SHA = pins["sha256"]
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    sdk = Path(os.environ["SEVEN_SDK"]).resolve()
    if not sdk.is_relative_to(temp) or not os.access("/dev/kvm", os.R_OK | os.W_OK):
        raise RuntimeError("Owned SDK and usable KVM required; no TCG fallback")
    out = Path(os.environ["GITHUB_WORKSPACE"]) / "output/seven-code8-720p-runtime"
    frames = out / "native-frames"
    frames.mkdir(parents=True, exist_ok=True)
    input_dir = temp / "seven-code8-720p-input"
    apk = input_dir / APK_NAME
    provenance = json.loads((input_dir / "fetch-provenance.json").read_text())
    if (apk.stat().st_size != pins["bytes"] or hashlib.sha256(apk.read_bytes()).hexdigest() != APK_SHA
            or provenance.get("assetId") != pins["assetId"] or provenance.get("apkSha256") != APK_SHA or provenance.get("releaseId") != pins["releaseId"]
            or provenance.get("versionCode") != 8
            or provenance.get("sourcePostOverridesInputsSha256") != "c4fd6196614ade90eb9b589788da4316acd6a4cbdbd71c68cb50d25408d96b5f"):
        raise RuntimeError("Relayed frozen APK/provenance mismatch")
    (out / "fetch-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    adb = str(sdk / "platform-tools/adb")
    emulator = str(sdk / "emulator/emulator")
    run_id = os.environ["GITHUB_RUN_ID"]
    avd = "SevenCode8_720p_" + run_id
    deadline = time.monotonic() + 900
    report = {"schemaVersion": 1, "projectId": "seven-district-reckoning", "status": "PREPARING",
        "runId": run_id, "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"), "physical": False,
        "deviceKind": "OFFICIAL_ANDROID_EMULATOR_KVM", "apkSha256": APK_SHA,
        "versionCode": 8, "ocrConfiguredMaximumSeconds": 60, "ocrChildOmpThreadLimit": 1,
        "flowAbsoluteDeadlineSeconds": 900, "gpuRequested": GPU_MODE, "accelRequested": "on",
        "experiment": "EXPLICIT_720P_PHONE_SIZE_SWANGLE_SAME_SIGNED_APK8_DIAGNOSTIC",
        "previous1920x1080Run": 38204855965, "previous1920x1080FailurePreserved": True,
        "deviceProfile": "pixel_2_with_owned_wm720x1280_override",
        "expectedOriginalNativeLandscapePNG": [1280,720], "nativeImagesResampled": False,
        "sourceQualityOrGameplayContentChanged": False, "pacingCauseProven": False,
        "furtherDeviceDiagnosticRepeatsAuthorized": False,
        "previousSwiftshaderFailureHistoryPreserved": True,
        "uniform261ShaderErrorFixedInGameSource": False,
        "automaticRendererFallback": False, "automaticEmulatorRestart": False,
        "bootVerified": False, "installedIdentityVerified": False, "startMenuObserved": False,
        "visibleStartTapped": False, "gameplayHudObserved": False, "movementGestureExecuted": False,
        "pauseResumeObserved": False, "retryCheckpointNoticeObserved": False,
        "warmRelaunchObserved": False, "sessionControlSmokeCaptured": False,
        "nativeGameplayAccepted": False, "nativeRuntimeReady": False, "firstChapterCompletedVerified": False,
        "gameSourceChangedByProbe": False, "candidateSourceOverrides": 3,
        "fiveMissionNativeLifecycleVerified": False, "gameStateInjected": False, "physicalDeviceRequirementSatisfied": False,
        "realTesterParticipationInferred": False, "storeWrites": 0, "captures": [], "inputs": [],
        "limits": ["Real native emulator frames and normal UI inputs; root visual acceptance remains required",
                   "Control-flow session is not an assertion that all five first-chapter missions completed",
                   "Emulator evidence is not physical iPhone/iPad proof or Google human opt-in evidence"]}
    proc = recorder = None
    remote_movie = None
    sequence = 0
    notice_dismissals = {"cold": 0, "warm": 0}
    system_ui_dump_attempts = 0  # Maximum2 official dumps across this whole900s flow.

    def save():
        (out / "native-observation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    def command(argv, timeout=20, allow_failure=False):
        if time.monotonic() >= deadline:
            raise RuntimeError("Absolute native observation deadline exceeded")
        result = subprocess.run(argv, capture_output=True, timeout=min(timeout, max(.1, deadline - time.monotonic())))
        if result.returncode and not allow_failure:
            raise RuntimeError("Owned native command failed: " + Path(argv[0]).name + " " + " ".join(argv[1:4]))
        return result

    def device(*args, timeout=20, allow_failure=False):
        return command([adb, "-s", SERIAL, *args], timeout, allow_failure)

    def capture(label):
        nonlocal sequence
        report["currentObservationPhase"] = label
        sequence += 1
        name = f"{sequence:03d}-{label}.png"
        capture_requested_at_utc = datetime.now(timezone.utc).isoformat()
        raw = device("exec-out", "screencap", "-p").stdout
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        path = frames / name
        path.write_bytes(raw)  # Preserve original dimensions/bytes even if the size guard fails.
        report["captures"].append({"name": name, "nativeWidth": image.width, "nativeHeight": image.height,
            "sha256": hashlib.sha256(raw).hexdigest(), "ocrComplete": False,
            "captureRequestedAtUtc": capture_requested_at_utc, "originalPNGWrittenAtUtc": datetime.now(timezone.utc).isoformat(),
            "nativeImageResampled": False, "originalLandscape720pVerified": False})
        save()
        report["captures"][-1]["originalLandscape720pVerified"] = verify_native_phone720_dimensions(image.width,image.height)
        save()
        ocr_argv = ["tesseract", str(path), "stdout", "-l", "chi_tra+eng", "--psm", "11", "tsv"]
        ocr_stdout, ocr_stderr, ocr_receipt = bounded_native_ocr(ocr_argv, deadline-time.monotonic())
        path.with_suffix(".ocr.stdout.txt").write_bytes(ocr_stdout)
        path.with_suffix(".ocr.stderr.txt").write_bytes(ocr_stderr)
        path.with_suffix(".tsv").write_bytes(ocr_stdout)
        ocr_receipt.update(nativeFrame=name, nativeFrameSha256=hashlib.sha256(raw).hexdigest(),
            argv=ocr_argv, stdoutFile=path.with_suffix(".ocr.stdout.txt").name,
            stderrFile=path.with_suffix(".ocr.stderr.txt").name)
        path.with_suffix(".ocr-receipt.json").write_text(json.dumps(ocr_receipt, indent=2)+"\n")
        report["captures"][-1]["ocrReceipt"] = ocr_receipt
        save()
        if ocr_receipt["timedOut"]:
            raise RuntimeError("OCR_CHILD_TIMEOUT_OMP1_WITHIN_REMAINING_FLOW_BUDGET: " + name)
        if ocr_receipt["exitCode"] != 0:
            raise RuntimeError("OCR_CHILD_NONZERO_STDERR_PRESERVED: " + name)
        ocr = ocr_stdout.decode("utf-8", "replace")
        text = " ".join(row.get("text", "") for row in csv.DictReader(io.StringIO(ocr), delimiter="\t", quoting=csv.QUOTE_NONE) if row.get("text"))
        report["captures"][-1].update(ocrComplete=True, ocrText=text[:4096])
        save()
        return image, ocr, name

    def wait_caption(caption, label, seconds=30):
        until = min(deadline, time.monotonic() + seconds)
        while time.monotonic() < until:
            if proc is not None and proc.poll() is not None:
                raise RuntimeError("Owned emulator exited before visible UI proof")
            image, tsv, name = capture(label)
            if normalized(caption) == normalized("開始新遊戲"):
                launch = "warm" if label.startswith("warm") else "cold"
                if dismiss_systemui_notice(label + "-late-notice", image, tsv, name, launch):
                    continue  # Observe a new actual frame after this one legitimate notice tap.
            box = label_box(tsv, caption)
            if box:
                return image, tsv, name, box
            time.sleep(3 if seconds <= 30 else 10)
        raise RuntimeError("Visible caption not observed within bound: " + caption)

    def tap_caption(caption, label, seconds=30):
        image, tsv, basis, box = wait_caption(caption, label, seconds)
        point = [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2]
        if not (0 <= point[0] < image.width and 0 <= point[1] < image.height):
            raise RuntimeError("OCR tap outside original native frame")
        report["inputs"].append({"action": "tap", "caption": caption, "basisNativeFrame": basis,
                                  "observedTextBox": box, "nativePoint": point})
        save()
        device("shell", "input", "tap", *map(str, point))
        time.sleep(1)

    def dismiss_systemui_notice(label, image=None, tsv=None, basis=None, launch="cold"):
        nonlocal system_ui_dump_attempts
        if image is None:
            image, tsv, basis = capture(label)
        if notice_dismissals[launch] >= 1:
            return False
        if not (label_box(tsv, "Viewing full screen")
                and label_box(tsv, "To exit, swipe down from the top of your screen")):
            report.setdefault("systemUiNoticeChecks", []).append({"basisNativeFrame": basis,
                "launch": launch, "result": "FULLSCREEN_EDUCATION_BODY_NOT_VISIBLE", "tapPerformed": False})
            save()
            return False  # A blank first frame does not suppress a later legitimate notice.
        xml = None
        while system_ui_dump_attempts < 2:
            system_ui_dump_attempts += 1
            number = system_ui_dump_attempts
            remote_xml = "/sdcard/SevenCode8_720p_" + run_id + "_notice_" + str(number) + ".xml"
            prefix = frames / (Path(basis).stem + ".uiautomator-attempt-" + str(number))
            record = {"attempt":number, "maximumFlowAttempts":2, "launch":launch,
                "basisNativeFrame":basis, "remoteXMLPath":remote_xml,
                "requestedAtUtc":datetime.now(timezone.utc).isoformat(), "validActualXML":False, "tapPerformed":False}
            report.setdefault("systemUiDumpAttempts", []).append(record)
            save()
            began = time.monotonic()
            try:
                dumped = device("shell", "uiautomator", "dump", remote_xml, timeout=30, allow_failure=True)
                dump_stdout, dump_stderr, dump_exit, dump_timed_out = dumped.stdout, dumped.stderr, dumped.returncode, False
            except subprocess.TimeoutExpired as error:
                dump_stdout, dump_stderr, dump_exit, dump_timed_out = error.stdout or b"", error.stderr or b"", None, True
            prefix.with_suffix(prefix.suffix+".dump.stdout.txt").write_bytes(dump_stdout)
            prefix.with_suffix(prefix.suffix+".dump.stderr.txt").write_bytes(dump_stderr)
            record["dump"] = {"argv":["adb","-s",SERIAL,"shell","uiautomator","dump",remote_xml], "exitCode":dump_exit, "timedOut":dump_timed_out,
                "elapsedSeconds":round(time.monotonic()-began,6), "stdoutBytes":len(dump_stdout), "stderrBytes":len(dump_stderr)}
            save()
            began = time.monotonic()
            try:
                cat = device("exec-out", "cat", remote_xml, timeout=20, allow_failure=True)
                cat_stdout, cat_stderr, cat_exit, cat_timed_out = cat.stdout, cat.stderr, cat.returncode, False
            except subprocess.TimeoutExpired as error:
                cat_stdout, cat_stderr, cat_exit, cat_timed_out = error.stdout or b"", error.stderr or b"", None, True
            prefix.with_suffix(prefix.suffix+".cat.stdout.txt").write_bytes(cat_stdout)
            prefix.with_suffix(prefix.suffix+".cat.stderr.txt").write_bytes(cat_stderr)
            xml, validity = actual_uiautomator_xml(cat_stdout,cat_stderr,cat_exit)
            if dump_exit != 0 or dump_timed_out:
                xml, validity = None, "OFFICIAL_DUMP_FAILED_OR_TIMEOUT"
            record["cat"] = {"argv":["adb","-s",SERIAL,"exec-out","cat",remote_xml], "exitCode":cat_exit,"timedOut":cat_timed_out,
                "elapsedSeconds":round(time.monotonic()-began,6), "stdoutBytes":len(cat_stdout), "stderrBytes":len(cat_stderr)}
            record.update(validActualXML=xml is not None, validity=validity, completedAtUtc=datetime.now(timezone.utc).isoformat())
            prefix.with_suffix(prefix.suffix+".receipt.json").write_text(json.dumps(record,indent=2)+"\n")
            save()
            if xml is not None:
                (frames/(Path(basis).stem+".uiautomator.xml")).write_text(xml)
                break
            if system_ui_dump_attempts >= 2 or deadline-time.monotonic() <= 2:
                break
            record["shortWaitBeforeNextActualDumpSeconds"] = 2
            save()
            time.sleep(2)  # Bounded once, inside the original900s deadline.
            image,tsv,basis = capture(label+"-xml-retry-frame")
            if not (label_box(tsv,"Viewing full screen") and label_box(tsv,"To exit, swipe down from the top of your screen")):
                report.setdefault("systemUiNoticeChecks",[]).append({"basisNativeFrame":basis,
                    "launch":launch,"result":"NOTICE_BODY_ABSENT_ON_NEW_ACTUAL_FRAME","tapPerformed":False})
                save()
                return False
        if xml is None:
            report["infrastructureHoldReason"] = "SYSTEMUI_XML_UNAVAILABLE_AFTER_AT_MOST2_OFFICIAL_DUMPS"
            report["performanceGateStatus"] = "NOT_RUN_OBSERVER_XML_UNAVAILABLE"
            report["performanceAttemptCount"] = 0
            save()
            raise RuntimeError("SYSTEMUI_XML_UNAVAILABLE; no ownership proof, no tap, no performance result")
        notice = system_ui_notice_from_frame(xml, image.width, image.height, tsv, notice_dismissals[launch])
        record["ownedPackageSamePanelMatched"] = notice is not None
        prefix.with_suffix(prefix.suffix+".receipt.json").write_text(json.dumps(record,indent=2)+"\n")
        if notice is None:
            report.setdefault("systemUiNoticeChecks", []).append({"basisNativeFrame": basis,
                "launch": launch, "result": "NO_UNIQUE_VISIBLE_OWNED_SAME_PANEL_NOTICE", "tapPerformed": False})
            save()
            return False
        box = notice["buttonBounds"]
        point = [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2]
        action = {"action": "dismiss_systemui_fullscreen_notice", "caption": "Got it",
            "package": "com.android.systemui", "basisNativeFrame": basis, "xmlBounds": box,
            "launch": launch, "nativePoint": point, "permissionGrant": False,
            "samePanelEvidence": notice, "commandSucceeded": False}
        report["inputs"].append(action)
        save()
        device("shell", "input", "tap", *map(str, point))
        action["commandSucceeded"] = True
        record["tapPerformed"] = True
        record["actualTapPoint"] = point
        prefix.with_suffix(prefix.suffix+".receipt.json").write_text(json.dumps(record,indent=2)+"\n")
        notice_dismissals[launch] += 1
        report["systemUiNoticeDismissals"] = dict(notice_dismissals)
        time.sleep(1)
        capture(label + "-after-dismiss")
        return True

    def hud(label):
        image, tsv, name, _ = wait_caption("MAIN", label, seconds=30)
        if not (label_box(tsv, "攻擊") and label_box(tsv, "暫停")):
            raise RuntimeError("Mission text without normal action HUD is not gameplay readiness")
        return image, tsv, name

    def movement(label):
        image, tsv, basis = hud(label + "-before")
        gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
        roi = gray[int(image.height * .66):, :int(image.width * .23)]
        circles = cv2.HoughCircles(roi, cv2.HOUGH_GRADIENT, dp=1.2, minDist=15,
                                  param1=80, param2=24, minRadius=22, maxRadius=int(image.height * .17))
        values = [] if circles is None else [[float(x), float(y + int(image.height * .66)), float(rad)] for x, y, rad in circles[0]]
        values = [x for x in values if x[0] < image.width * .2 and x[1] > image.height * .72]
        if not values:
            raise RuntimeError("Visible native joystick ring not identified; no coordinate guessed")
        values.sort(key=lambda row: row[2], reverse=True)
        circle = values[0]
        if any(abs(row[0] - circle[0]) + abs(row[1] - circle[1]) > circle[2] for row in values[1:]):
            raise RuntimeError("Multiple native joystick candidates; no gesture guessed")
        x, y, radius = circle
        gesture = [round(x), round(y), round(x + radius * .72), round(y), 1800]
        report["inputs"].append({"action": "joystick_swipe", "basisNativeFrame": basis,
            "observedCircleCandidates": values, "selectedCircle": circle, "nativeGesture": gesture})
        save()
        device("shell", "input", "swipe", *map(str, gesture))
        time.sleep(.5)
        after, _, after_name = hud(label + "-after")
        crop = (int(image.width * .18), int(image.height * .34), int(image.width * .82), int(image.height * .70))
        difference = np.asarray(ImageChops.difference(image.crop(crop), after.crop(crop)))
        report.setdefault("movementFrameDifferences", []).append({"before": basis, "after": after_name,
            "comparisonCrop": list(crop), "fractionPixelsChannelDeltaAbove20": float((difference.max(axis=2) > 20).mean()),
            "pixelChangeAloneIsNotPlayerPhysicsAcceptance": True})
        report["movementGestureExecuted"] = True
        save()

    try:
        cert = command([str(sdk / "build-tools/36.1.0/apksigner"), "verify", "--print-certs", str(apk)]).stdout.decode()
        actual = re.findall(r"certificate SHA-256 digest: ([0-9a-f]{64})", cert)
        if actual != [CERT_SHA]:
            raise RuntimeError("Exact release certificate mismatch")
        report["certificateSha256Verified"] = actual[0]
        accel = command([emulator, "-accel-check"])
        accel_text = (accel.stdout + accel.stderr).decode("utf-8", "replace")
        if "KVM" not in accel_text or "usable" not in accel_text.lower():
            raise RuntimeError("Official usable KVM acceleration not established")
        report["actualAccelCheck"] = accel_text
        gpu_help = command([emulator, "-help-gpu"], allow_failure=True)
        (out / "emulator-help-gpu.stdout.txt").write_bytes(gpu_help.stdout)
        (out / "emulator-help-gpu.stderr.txt").write_bytes(gpu_help.stderr)
        report["officialGpuHelp"] = {"exitCode": gpu_help.returncode,
            "explicitSwangleAdvertised": verify_swangle_gpu_help(
                gpu_help.stdout.decode("utf-8", "replace"),
                gpu_help.stderr.decode("utf-8", "replace"), gpu_help.returncode)}
        save()
        attached = command([adb, "devices"]).stdout.decode().strip().splitlines()[1:]
        if any(line.strip() for line in attached):
            raise RuntimeError("Fresh runner already has an unexpected device; no reuse")
        for port in [5580, 5581]:
            with socket.socket() as reserved:
                reserved.bind(("127.0.0.1", port))
        manager = str(sdk / "cmdline-tools/latest/bin/avdmanager")
        avd_home = Path(os.environ["ANDROID_AVD_HOME"]).resolve()
        user_home = Path(os.environ["ANDROID_USER_HOME"]).resolve()
        if avd_home != temp / "seven-code8-720p-avds" or user_home != temp / "seven-code8-720p-user":
            raise RuntimeError("Fixed owned AVD/user homes differ")
        # The official Java manager may fall back when an override directory does
        # not exist. Establish both owned homes before the one create call.
        avd_home.mkdir(parents=True, exist_ok=True)
        user_home.mkdir(parents=True, exist_ok=True)
        data_path = avd_home / (avd + ".avd")
        registry_path = avd_home / (avd + ".ini")
        if registry_path.exists() or data_path.exists():
            raise RuntimeError("Owned AVD name/data already exist; no overwrite or retry")
        report["ownedAvdPrecreate"] = {"avdHome": str(avd_home), "userHome": str(user_home),
            "avdHomeExists": avd_home.is_dir(), "userHomeExists": user_home.is_dir(),
            "expectedRegistry": str(registry_path), "expectedData": str(data_path)}
        save()
        try:
            result = subprocess.run([manager, "create", "avd", "-n", avd, "-k",
                "system-images;android-36;google_apis;x86_64", "--device", "pixel_2", "--path", str(data_path)],
                input=b"no\n", capture_output=True, timeout=75)
        except subprocess.TimeoutExpired as error:
            (out / "avd-create.stdout.txt").write_bytes((error.stdout or b"")[:1024 * 1024])
            (out / "avd-create.stderr.txt").write_bytes((error.stderr or b"")[:1024 * 1024])
            report["officialAvdCreate"] = {"exitCode": None, "timedOut": True}
            save()
            raise RuntimeError("Official AVD create deadline exceeded before boot") from None
        (out / "avd-create.stdout.txt").write_bytes(result.stdout[:1024 * 1024])
        (out / "avd-create.stderr.txt").write_bytes(result.stderr[:1024 * 1024])
        report["officialAvdCreate"] = {"exitCode": result.returncode,
            "stdoutBytes": len(result.stdout), "stderrBytes": len(result.stderr),
            "stdoutTruncated": len(result.stdout) > 1024 * 1024,
            "stderrTruncated": len(result.stderr) > 1024 * 1024}
        save()
        if result.returncode:
            raise RuntimeError("Canonical isolated avdmanager create failed before boot")
        if registry_path.is_file():
            (out / "owned-avd-registry.ini.txt").write_bytes(registry_path.read_bytes())
        if (data_path / "config.ini").is_file():
            (out / "owned-avd-config.ini.txt").write_bytes((data_path / "config.ini").read_bytes())
        listing = command([emulator, "-list-avds"], allow_failure=True)
        (out / "emulator-list-avds.stdout.txt").write_bytes(listing.stdout)
        (out / "emulator-list-avds.stderr.txt").write_bytes(listing.stderr)
        if listing.returncode:
            raise RuntimeError("Official emulator AVD discovery failed before boot")
        report["ownedAvdRegistry"] = verify_avd_registry(registry_path, data_path, avd,
                                                        listing.stdout.decode("utf-8"), temp)
        (out / "owned-avd-prelaunch-proof.json").write_text(json.dumps(report["ownedAvdRegistry"], indent=2) + "\n")
        save()
        bootlog = (out / "owned-emulator.log").open("wb")
        proc = subprocess.Popen([emulator, "-avd", avd, "-no-window", "-no-boot-anim", "-no-snapshot",
            "-no-audio", "-accel", "on", "-gpu", GPU_MODE, "-memory", "2048", "-cores", "2",
            "-camera-back", "none", "-camera-front", "none", "-port", "5580"], stdout=bootlog, stderr=subprocess.STDOUT,
            start_new_session=True)
        report["ownedAvdName"] = avd
        report["ownedEmulatorPid"] = proc.pid
        boot_until = time.monotonic() + 180
        while time.monotonic() < boot_until:
            result = device("shell", "getprop", "sys.boot_completed", allow_failure=True)
            if result.returncode == 0 and result.stdout.strip() == b"1":
                break
            if proc.poll() is not None:
                raise RuntimeError("Owned KVM emulator exited before boot completion")
            time.sleep(3)
        else:
            raise RuntimeError("Owned KVM boot deadline exceeded")
        guest_abi = device("shell", "getprop", "ro.product.cpu.abilist64").stdout.decode().strip()
        bridge = device("shell", "getprop", "ro.dalvik.vm.native.bridge").stdout.decode().strip()
        if "arm64-v8a" not in guest_abi.split(",") or bridge != "libndk_translation.so":
            raise RuntimeError("Actual guest ARM64 bridge absent; no injection allowed")
        report.update(bootVerified=True, actualGuestAbi64=guest_abi, actualGuestNativeBridge=bridge)
        actual_boot_log = (out / "owned-emulator.log").read_text(encoding="utf-8", errors="replace")
        report["actualSwangleGlesSelectionVerified"] = verify_swangle_boot_selection(actual_boot_log)
        report["actualGraphicsModeLines"] = [line for line in actual_boot_log.splitlines()
            if any(key in line for key in ["emuglConfig_init", "Graphics Adapter", "Graphics API Version"])]
        save()
        wm_before = device("shell","wm","size")
        (out/"owned-wm-size-before.stdout.txt").write_bytes(wm_before.stdout)
        (out/"owned-wm-size-before.stderr.txt").write_bytes(wm_before.stderr)
        if "Override size:" in wm_before.stdout.decode("utf-8","replace"):
            raise RuntimeError("Fresh owned guest has prior size override; no overwrite or retry")
        wm_set = device("shell","wm","size","720x1280",allow_failure=True)
        (out/"owned-wm-size-set.stdout.txt").write_bytes(wm_set.stdout)
        (out/"owned-wm-size-set.stderr.txt").write_bytes(wm_set.stderr)
        if wm_set.returncode:
            raise RuntimeError("One official owned wm720x1280 override failed; no fallback/retry")
        wm_after = device("shell","wm","size")
        (out/"owned-wm-size-after.stdout.txt").write_bytes(wm_after.stdout)
        (out/"owned-wm-size-after.stderr.txt").write_bytes(wm_after.stderr)
        report["ownedDeviceSizeReadback"] = verify_phone720_wm_readback(wm_after.stdout.decode("utf-8","replace"))
        report["ownedDeviceSizeReadback"].update(command=["adb","-s",SERIAL,"shell","wm","size","720x1280"],
            appliedBeforeInstallAndLaunch=True, appAlreadyLaunched=False, densityChanged=False,
            guestOnly=True, priorRunModified=False, actualMutationAttempts=1)
        (out/"owned-720p-device-profile.json").write_text(json.dumps(report["ownedDeviceSizeReadback"],indent=2)+"\n")
        save()
        device("shell", "input", "keyevent", "82")
        device("install", "-r", str(apk), timeout=90)
        package = device("shell", "dumpsys", "package", PACKAGE).stdout.decode()
        if not re.search(r"versionCode=8\b", package) or "versionName=1.0.0" not in package:
            raise RuntimeError("Installed fixed package/version differs")
        resolved = device("shell", "cmd", "package", "resolve-activity", "--brief", PACKAGE).stdout.decode().strip().splitlines()[-1]
        if resolved != ALIAS:
            raise RuntimeError("Actual MAIN launcher alias differs; no non-exported activity attempted")
        report.update(installedIdentityVerified=True, resolvedActivity=resolved)
        device("logcat", "-c")
        start = device("shell", "am", "start", "-W", "-n", ALIAS, timeout=45).stdout.decode()
        report["actualStartCommandOutput"] = start
        pid_text = device("shell", "pidof", PACKAGE, allow_failure=True).stdout.decode().strip()
        if re.fullmatch(r"[1-9][0-9]*", pid_text):
            report["ownedAppPidAtLaunch"] = int(pid_text)
        dismiss_systemui_notice("cold-systemui-notice")
        wait_caption("開始新遊戲", "cold-title-wait", seconds=360)
        report["startMenuObserved"] = True
        save()
        remote_movie = "/sdcard/SevenCode8_720p_" + run_id + ".mp4"
        recorder = subprocess.Popen([adb, "-s", SERIAL, "shell", "screenrecord", "--time-limit", "90", remote_movie],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tap_caption("開始新遊戲", "observed-start")
        report["visibleStartTapped"] = True
        hud("after-visible-start")
        report["gameplayHudObserved"] = True
        movement("movement-one")
        tap_caption("攻擊", "observed-attack")
        capture("after-observed-attack")
        tap_caption("暫停", "observed-pause")
        wait_caption("繼續遊戲", "pause-menu")
        tap_caption("繼續遊戲", "observed-resume")
        hud("after-resume")
        report["pauseResumeObserved"] = True
        movement("movement-two")
        tap_caption("暫停", "observed-pause-for-retry")
        # Scroll the observed pause menu only when the actual Retry caption is offscreen.
        for index in range(4):
            image, tsv, basis = capture("pause-retry-scroll")
            if label_box(tsv, "重試目前任務"):
                break
            if index == 3:
                raise RuntimeError("Retry not observed after bounded normal menu scrolling")
            gesture = [image.width // 2, round(image.height * .77), image.width // 2, round(image.height * .37), 650]
            report["inputs"].append({"action": "pause_menu_scroll", "basisNativeFrame": basis, "nativeGesture": gesture})
            device("shell", "input", "swipe", *map(str, gesture))
            time.sleep(.4)
        tap_caption("重試目前任務", "observed-retry")
        wait_caption("已回到本段檢查點", "retry-result", seconds=10)
        hud("after-retry")
        report["retryCheckpointNoticeObserved"] = True
        device("shell", "am", "force-stop", PACKAGE)
        device("shell", "am", "start", "-W", "-n", ALIAS, timeout=45)
        dismiss_systemui_notice("warm-systemui-notice", launch="warm")
        wait_caption("開始新遊戲", "warm-title-wait", seconds=120)
        tap_caption("開始新遊戲", "warm-visible-start")
        hud("warm-gameplay")
        report["warmRelaunchObserved"] = True
        report["sessionControlSmokeCaptured"] = True
        report["status"] = "NATIVE_CONTROL_FLOW_CAPTURED_PENDING_ROOT_VISUAL_GAMEPLAY_ACCEPTANCE"
        if recorder is not None:
            recorder.wait(timeout=95)
            movie = out / "SevenCode8-native-emulator-control-flow.mp4"
            device("pull", remote_movie, str(movie), timeout=60)
            if movie.is_file() and movie.stat().st_size > 0:
                report["nativeMovie"] = {"file": movie.name, "bytes": movie.stat().st_size,
                                         "sha256": hashlib.sha256(movie.read_bytes()).hexdigest(), "physical": False}
        save()
        print(report["status"], flush=True)
    except Exception as error:
        report["status"] = "FAILED_NATIVE_OBSERVATION"
        report["errorType"] = type(error).__name__
        report["error"] = str(error)[:1000]
        report["remainingPerformanceAcceptanceGate"] = ("NOT_RUN_OBSERVER_XML_UNAVAILABLE" if report.get("infrastructureHoldReason")
            else "REAL_ARM_DEVICE_REQUIRED_IF_THIS_ONE720P_DIAGNOSTIC_STILL_LOADING; retain hold, no repeated emulator guesses")
        report["ownedEmulatorExitAtFailure"] = proc.poll() if proc is not None else None
        save()
        raise
    finally:
        if proc is not None:
            try:
                # Cleanup is bounded separately and still runs after the observation deadline.
                if report["bootVerified"]:
                    try:
                        app_pid = report.get("ownedAppPidAtLaunch")
                        if type(app_pid) is int and app_pid > 0:
                            app_log = subprocess.run([adb, "-s", SERIAL, "logcat", "-d", "--pid=" + str(app_pid),
                                                      "-v", "threadtime"], capture_output=True, timeout=20).stdout
                            (out / "owned-app-renderer-logcat.txt").write_bytes(app_log[:4 * 1024 * 1024])
                            report["ownedAppRendererLogcatTruncated"] = len(app_log) > 4 * 1024 * 1024
                            app_text = app_log.decode("utf-8", "replace")
                            report["ownedAppRendererLines"] = [line for line in app_text.splitlines()
                                if any(key in line for key in ["renderingDevice:", "renderer:", "OpenGL API", "Godot Engine"])]
                            report["ownedAppUniformVectorErrorObserved"] = "GL_MAX_FRAGMENT_UNIFORM_VECTORS" in app_text
                        log = subprocess.run([adb, "-s", SERIAL, "logcat", "-d", "-v", "threadtime"],
                                             capture_output=True, timeout=20).stdout
                        (out / "owned-guest-logcat.txt").write_bytes(log[:4 * 1024 * 1024])
                        report["guestLogcatTruncated"] = len(log) > 4 * 1024 * 1024
                    except subprocess.TimeoutExpired:
                        report["guestLogcatUnavailableReason"] = "BOOTED_GUEST_LOGCAT_TIMEOUT"
                else:
                    report["guestLogcatUnavailableReason"] = "NO_BOOTED_GUEST"
                if recorder is not None and "nativeMovie" not in report:
                    try:
                        recorder.wait(timeout=95)
                        movie = out / "SevenCode8-native-emulator-control-flow.mp4"
                        result = subprocess.run([adb, "-s", SERIAL, "pull", remote_movie, str(movie)],
                                                capture_output=True, timeout=45)
                        if result.returncode == 0 and movie.is_file() and movie.stat().st_size > 0:
                            report["nativeMovie"] = {"file": movie.name, "bytes": movie.stat().st_size,
                                "sha256": hashlib.sha256(movie.read_bytes()).hexdigest(), "physical": False,
                                "scenarioFailed": report["status"] == "FAILED_NATIVE_OBSERVATION"}
                    except subprocess.TimeoutExpired:
                        recorder.terminate()
                        report["nativeMovieFinalizationVerified"] = False
                if proc.poll() is None:
                    actual_avd = subprocess.run([adb, "-s", SERIAL, "emu", "avd", "name"],
                                                capture_output=True, timeout=10).stdout.decode().splitlines()
                    if actual_avd and actual_avd[0] == avd:
                        subprocess.run([adb, "-s", SERIAL, "emu", "kill"], capture_output=True, timeout=10)
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGTERM)  # Only the child group created above.
                        proc.wait(timeout=10)
                report["ownedEmulatorStopped"] = proc.poll() is not None
                report["ownedEmulatorExitCode"] = proc.poll()
            except Exception as error:
                report["cleanupErrorType"] = type(error).__name__
            save()


if __name__ == "__main__":
    main()
