"""One exact Seven6 Android KVM observation through normal adb UI input only.

No app source, pack, save, mission or object state is edited. Captured control
flow is separate from root visual gameplay acceptance and first-chapter completion.
"""
import csv
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
import numpy as np

PACKAGE = "tw.mars.sevendistrictreckoning"
ALIAS = PACKAGE + "/com.godot.game.GodotAppLauncher"
APK_NAME = "seven-district-reckoning-1.0.0-build6.apk"
APK_SHA = "f72044f7b2c1a1fb44b099128b8e7446fc3ba8531c8946b1dddd7e5f7482bee7"
CERT_SHA = "1dd3cc96a02e4555e8d91a42d749a019ee5c4781d4d7510947ae48c865e21110"
SERIAL = "emulator-5580"


def normalized(value):
    return re.sub(r"[^A-Za-z0-9\u3400-\u9fff]", "", value).casefold()


def label_box(tsv, caption):
    lines = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
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


def main():
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != "mars-tw/taiwan-train-math"
            or os.environ.get("GITHUB_REF") != "refs/heads/codex/ashes-simulator-recording"):
        raise RuntimeError("Fixed Seven QA branch only")
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    sdk = Path(os.environ["SEVEN_SDK"]).resolve()
    if not sdk.is_relative_to(temp) or not os.access("/dev/kvm", os.R_OK | os.W_OK):
        raise RuntimeError("Owned SDK and usable KVM required; no TCG fallback")
    out = Path(os.environ["GITHUB_WORKSPACE"]) / "output/seven-code6-runtime"
    frames = out / "native-frames"
    frames.mkdir(parents=True, exist_ok=True)
    input_dir = temp / "seven-code6-input"
    apk = input_dir / APK_NAME
    provenance = json.loads((input_dir / "fetch-provenance.json").read_text())
    if (apk.stat().st_size != 42696838 or hashlib.sha256(apk.read_bytes()).hexdigest() != APK_SHA
            or provenance.get("assetId") != 632341589 or provenance.get("apkSha256") != APK_SHA):
        raise RuntimeError("Relayed frozen APK/provenance mismatch")
    (out / "fetch-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    adb = str(sdk / "platform-tools/adb")
    emulator = str(sdk / "emulator/emulator")
    run_id = os.environ["GITHUB_RUN_ID"]
    avd = "SevenCode6_" + run_id
    deadline = time.monotonic() + 900
    report = {"schemaVersion": 1, "projectId": "seven-district-reckoning", "status": "PREPARING",
        "runId": run_id, "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"), "physical": False,
        "deviceKind": "OFFICIAL_ANDROID_EMULATOR_KVM", "apkSha256": APK_SHA,
        "versionCode": 6, "gpuRequested": "swiftshader", "accelRequested": "on",
        "automaticRendererFallback": False, "automaticEmulatorRestart": False,
        "bootVerified": False, "installedIdentityVerified": False, "startMenuObserved": False,
        "visibleStartTapped": False, "gameplayHudObserved": False, "movementGestureExecuted": False,
        "pauseResumeObserved": False, "retryCheckpointNoticeObserved": False,
        "warmRelaunchObserved": False, "sessionControlSmokeCaptured": False,
        "nativeGameplayAccepted": False, "nativeRuntimeReady": False, "firstChapterCompletedVerified": False,
        "gameSourceChanged": False, "gameStateInjected": False, "physicalDeviceRequirementSatisfied": False,
        "realTesterParticipationInferred": False, "storeWrites": 0, "captures": [], "inputs": [],
        "limits": ["Real native emulator frames and normal UI inputs; root visual acceptance remains required",
                   "Control-flow session is not an assertion that all five first-chapter missions completed",
                   "Emulator evidence is not physical iPhone/iPad proof or Google human opt-in evidence"]}
    proc = recorder = None
    remote_movie = None
    sequence = 0

    def save():
        (out / "native-observation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    def command(argv, timeout=20, allow_failure=False):
        if time.monotonic() >= deadline:
            raise RuntimeError("Absolute native observation deadline exceeded")
        result = subprocess.run(argv, capture_output=True, timeout=timeout)
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
        raw = device("exec-out", "screencap", "-p").stdout
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        if image.width < 600 or image.height < 300 or image.width * image.height > 5000000:
            raise RuntimeError("Native viewport unexpectedly small or oversized")
        path = frames / name
        path.write_bytes(raw)
        ocr = command(["tesseract", str(path), "stdout", "-l", "chi_tra+eng", "--psm", "11", "tsv"], timeout=25).stdout.decode("utf-8", "replace")
        path.with_suffix(".tsv").write_text(ocr)
        text = " ".join(row.get("text", "") for row in csv.DictReader(io.StringIO(ocr), delimiter="\t") if row.get("text"))
        report["captures"].append({"name": name, "nativeWidth": image.width, "nativeHeight": image.height,
                                   "sha256": hashlib.sha256(raw).hexdigest(), "ocrText": text[:4096]})
        save()
        return image, ocr, name

    def wait_caption(caption, label, seconds=30):
        until = min(deadline, time.monotonic() + seconds)
        while time.monotonic() < until:
            if proc is not None and proc.poll() is not None:
                raise RuntimeError("Owned emulator exited before visible UI proof")
            image, tsv, name = capture(label)
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

    def dismiss_systemui_notice(label):
        image, tsv, basis = capture(label)
        remote_xml = "/sdcard/SevenCode6_" + run_id + "_notice.xml"
        device("shell", "uiautomator", "dump", remote_xml, timeout=30)
        xml = device("exec-out", "cat", remote_xml).stdout.decode("utf-8", "replace")
        (frames / (Path(basis).stem + ".uiautomator.xml")).write_text(xml)
        box = system_ui_notice_box(xml, image.width, image.height)
        if box is None:
            report.setdefault("systemUiNoticeChecks", []).append({"basisNativeFrame": basis,
                "result": "NO_UNIQUE_VISIBLE_SYSTEMUI_GOT_IT_NOTICE", "tapPerformed": False})
            save()
            return
        visible_caption = label_box(tsv, "Got it")
        if visible_caption is None:
            raise RuntimeError("SystemUI XML notice caption not visible in original frame OCR; no tap")
        caption_center = [(visible_caption[0] + visible_caption[2]) // 2,
                          (visible_caption[1] + visible_caption[3]) // 2]
        if not (box[0] <= caption_center[0] < box[2] and box[1] <= caption_center[1] < box[3]):
            raise RuntimeError("SystemUI caption frame/XML mismatch; no tap")
        point = [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2]
        report["inputs"].append({"action": "dismiss_systemui_fullscreen_notice", "caption": "Got it",
            "package": "com.android.systemui", "basisNativeFrame": basis, "xmlBounds": box,
            "nativePoint": point, "permissionGrant": False})
        save()
        device("shell", "input", "tap", *map(str, point))
        time.sleep(1)
        capture(label + "-after-dismiss")

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
        attached = command([adb, "devices"]).stdout.decode().strip().splitlines()[1:]
        if any(line.strip() for line in attached):
            raise RuntimeError("Fresh runner already has an unexpected device; no reuse")
        for port in [5580, 5581]:
            with socket.socket() as reserved:
                reserved.bind(("127.0.0.1", port))
        manager = str(sdk / "cmdline-tools/latest/bin/avdmanager")
        result = subprocess.run([manager, "create", "avd", "-n", avd, "-k",
            "system-images;android-36;google_apis;x86_64", "--device", "pixel_2"],
            input=b"no\n", capture_output=True, timeout=75)
        if result.returncode:
            (out / "avd-create.stderr.txt").write_bytes(result.stderr)
            raise RuntimeError("Canonical isolated avdmanager create failed before boot")
        bootlog = (out / "owned-emulator.log").open("wb")
        proc = subprocess.Popen([emulator, "-avd", avd, "-no-window", "-no-boot-anim", "-no-snapshot",
            "-no-audio", "-accel", "on", "-gpu", "swiftshader", "-memory", "2048", "-cores", "2",
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
        device("shell", "input", "keyevent", "82")
        device("install", "-r", str(apk), timeout=90)
        package = device("shell", "dumpsys", "package", PACKAGE).stdout.decode()
        if not re.search(r"versionCode=6\b", package) or "versionName=1.0.0" not in package:
            raise RuntimeError("Installed fixed package/version differs")
        resolved = device("shell", "cmd", "package", "resolve-activity", "--brief", PACKAGE).stdout.decode().strip().splitlines()[-1]
        if resolved != ALIAS:
            raise RuntimeError("Actual MAIN launcher alias differs; no non-exported activity attempted")
        report.update(installedIdentityVerified=True, resolvedActivity=resolved)
        device("logcat", "-c")
        start = device("shell", "am", "start", "-W", "-n", ALIAS, timeout=45).stdout.decode()
        report["actualStartCommandOutput"] = start
        dismiss_systemui_notice("cold-systemui-notice")
        wait_caption("開始新遊戲", "cold-title-wait", seconds=360)
        report["startMenuObserved"] = True
        save()
        remote_movie = "/sdcard/SevenCode6_" + run_id + ".mp4"
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
        dismiss_systemui_notice("warm-systemui-notice")
        wait_caption("開始新遊戲", "warm-title-wait", seconds=120)
        tap_caption("開始新遊戲", "warm-visible-start")
        hud("warm-gameplay")
        report["warmRelaunchObserved"] = True
        report["sessionControlSmokeCaptured"] = True
        report["status"] = "NATIVE_CONTROL_FLOW_CAPTURED_PENDING_ROOT_VISUAL_GAMEPLAY_ACCEPTANCE"
        if recorder is not None:
            recorder.wait(timeout=95)
            movie = out / "SevenCode6-native-emulator-control-flow.mp4"
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
        report["ownedEmulatorExitAtFailure"] = proc.poll() if proc is not None else None
        save()
        raise
    finally:
        if proc is not None:
            try:
                # Cleanup is bounded separately and still runs after the observation deadline.
                log = subprocess.run([adb, "-s", SERIAL, "logcat", "-d", "-v", "threadtime"],
                                     capture_output=True, timeout=20).stdout
                (out / "owned-guest-logcat.txt").write_bytes(log[:4 * 1024 * 1024])
                report["guestLogcatTruncated"] = len(log) > 4 * 1024 * 1024
                if recorder is not None and "nativeMovie" not in report:
                    try:
                        recorder.wait(timeout=95)
                        movie = out / "SevenCode6-native-emulator-control-flow.mp4"
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
