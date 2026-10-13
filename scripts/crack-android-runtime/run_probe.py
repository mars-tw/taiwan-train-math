"""One exact Crack2 Android KVM observation through normal adb UI input only.

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
from roi_ocr import find_caption as find_caption_roi, read_tsv, merge_tsv, map_box, caption_budget, FlowDeadlineExceeded, roi_rectangles, clipped_word_tsv

PACKAGE = "tw.mars.crackveilvanguard"
ALIAS = PACKAGE + "/com.godot.game.GodotAppLauncher"
APK_NAME = "crackveil-vanguard-1.0.0-build2.apk"
APK_SHA = "0b3a4aec652ce8cbb5110688670df3ef7d60bce28d13668c3fa6f22d5e54a8d2"
CERT_SHA = "7166f66b5a182f2330c380fd57bd6f2821247db519b59ab9abe5aa554968c797"
SERIAL = "emulator-5580"
GPU_MODE = "swangle"  # Fixed supported environment experiment; no product-source fix or fallback.
SOURCE_LEVEL_PREFIXES = ("Lv.", "等級")
SOURCE_SKILL_CAPTIONS = ("旋", "斬")
SOURCE_CAPTION_CONTRACT = {"hudSourceSha256":"4822ed136c3fc7a3127ba1f86b0f4020913e120c00b152af0d6c49b97f7360a3",
    "levelFormats":["Lv.%d", "等級 %d", "等級 %d   經驗 %d/%d"], "abilityButtonTexts":["旋", "斬"],
    "sourceLines":{"Lv":1304,"fallbackLevel":1713,"abilityButton":1917}}
SOURCE_OPTION_CAPTIONS = ('事件穹網', '五人滿編', '五分鐘防線', '偏壓改裝', '共鳴火花', '共鳴聖歌', '分裂燼彈', '剃界盾輪', '剪界星環', '單線協定', '回影追斬', '回收磁場', '回收餘波', '契約擴展', '契約槽 +1', '守門者倒下', '定向改裝', '帷幕王庭', '帷幕護盾', '招募：', '星環共鳴', '星盾和聲', '星盾重衛', '星裂貫槍', '星雷珠', '星雷羽鷹', '星霜聖域', '時輪刃衛', '時輪工坊', '曜砂王陵', '曜砂甲蟲', '月華靈森', '月華靈火', '武器覺醒', '殲滅 500', '流星雨', '深層急救', '深潮歌妖', '漸強和聲', '潮生祝禱', '灼星烙印', '焰尾靈狐', '焰爆術士', '燼脈聯爆', '燼雨連爆', '牧長裂約', '獵隙導引', '獵隙蜂群', '玻璃磁界', '珊潮遺都', '珊瑚巨衛', '疾步校準', '疾閃目擊', '短路超載', '砂影獵手', '磁暴回收', '磁滯目擊', '空槽', '精英信標', '精英餌標', '精英首獵', '緊急整補', '緋星熔庭', '縫獵協議', '翠晶花園', '翠玉靈兔', '脈衝餘燼', '蒼月空庭', '虛空錨點', '血稅', '裂光校準', '裂殖目擊', '裂線分叉', '裂群召喚師', '裂錨定駐', '裂隙急救', '裂隙扇編', '裂隙拾荒', '裂隙護甲', '裂隙過載', '裂隙韌性', '起始選擇 +1', '超載新星', '返刃共振', '追影刃', '逐金魔靈', '重整庫存', '金饑', '鏡裂群牧', '雷爪獵將', '雷鏈過載', '雷霆浮島', '霜晶槍', '霜環守望者', '靜幕', '餘燼井')


def locate_visible_joystick(image):
    """Find the source-defined lower-left cyan ring and bright central knob.

    The radius band and knob threshold are pinned to the fixed Crack2 native
    1920x1080 observation. Other layouts may fail closed; no coordinate fallback.
    """
    width, height = image.size
    if (width, height) != (1920, 1080):
        raise RuntimeError("Unexpected native frame size for pinned joystick locator")
    rgb = np.asarray(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    top, right = int(height * .66), int(width * .23)
    circles = cv2.HoughCircles(gray[top:, :right], cv2.HOUGH_GRADIENT,
        dp=1.2, minDist=int(height * .074), param1=80, param2=40,
        minRadius=int(height * .083), maxRadius=int(height * .125))
    geometric = []
    if circles is not None:
        for raw_x, raw_y, raw_radius in circles[0]:
            x, y, radius = float(raw_x), float(raw_y + top), float(raw_radius)
            if x < width * .2 and height * .72 < y < height * .96:
                geometric.append([x, y, radius])
    # The Godot source draws an arc around a filled knob. The old grayscale
    # Hough pass treated textured terrain as additional rings; require the
    # knob's observed light disk at the ring center before any gesture.
    verified = []
    for x, y, radius in geometric:
        knob_radius = radius * .22
        left = max(0, int(x - knob_radius))
        upper = max(0, int(y - knob_radius))
        right_edge = min(width, int(x + knob_radius) + 1)
        bottom = min(height, int(y + knob_radius) + 1)
        yy, xx = np.ogrid[upper:bottom, left:right_edge]
        disk = (xx - x) ** 2 + (yy - y) ** 2 <= knob_radius ** 2
        pixels = rgb[upper:bottom, left:right_edge][disk]
        bright_fraction = float(np.mean((pixels[:, 0] > 145) &
            (pixels[:, 1] > 155) & (pixels[:, 2] > 155)))
        if bright_fraction > .20:
            verified.append({"circle": [x, y, radius], "knobBrightFraction": bright_fraction})
    if not verified:
        raise RuntimeError("Visible native joystick ring and central knob not uniquely identified; no coordinate guessed")
    if len(verified) != 1:
        raise RuntimeError("Multiple spatial native joystick candidates with visible knobs; no gesture guessed")
    return geometric, verified[0]


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


def label_box(tsv, caption, *, contributing_rows=False):
    lines = {}
    _, rows = read_tsv(tsv)
    for row in rows:
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
    if not wanted:
        raise RuntimeError("Empty visible caption; no tap guessed")
    for words in lines.values():
        words.sort(key=lambda word: int(word["left"]))
        text, spans = "", []
        for word in words:
            start = len(text)
            text += normalized(word["text"])
            spans.append((start, len(text), word))
        start = text.find(wanted)
        if start < 0:
            continue
        if text.find(wanted, start + 1) >= 0:
            raise RuntimeError("Ambiguous visible caption; no tap guessed")
        contributing = [word for left, right, word in spans if right > start and left < start + len(wanted)]
        left = min(int(word["left"]) for word in contributing)
        top = min(int(word["top"]) for word in contributing)
        right = max(int(word["left"]) + int(word["width"]) for word in contributing)
        bottom = max(int(word["top"]) + int(word["height"]) for word in contributing)
        matches.append(([left, top, right, bottom], contributing))
    if len(matches) > 1:
        raise RuntimeError("Ambiguous visible caption; no tap guessed")
    return matches[0][1 if contributing_rows else 0] if matches else None


def exact_word_box(tsv, caption, *, contributing_rows=False):
    matches=[]
    for word in read_tsv(tsv)[1]:
        if word['level']=='5' and float(word['conf'])>=25 and word['text'].strip()==caption:
            left,top,width,height=(int(word[k]) for k in ['left','top','width','height'])
            matches.append(([left,top,left+width,top+height],[word]))
    if len(matches)>1:raise RuntimeError("Ambiguous exact skill caption; no tap guessed")
    return matches[0][1 if contributing_rows else 0] if matches else None


def source_level_box(tsv, caption, *, contributing_rows=False):
    patterns={"Lv.":r"(?<!\S)Lv\.\s*[0-9]+(?=\s|$)", "等級":r"(?<!\S)等\s*級\s*[0-9]+(?=\s|$)"}
    if caption not in patterns:raise RuntimeError("Unknown source level prefix")
    lines={}
    for word in read_tsv(tsv)[1]:
        if word['level']=='5' and float(word['conf'])>=25 and word['text'].strip():
            key=tuple(word[k] for k in ['page_num','block_num','par_num','line_num'])
            lines.setdefault(key,[]).append(word)
    matches=[]
    for words in lines.values():
        words.sort(key=lambda word:int(word['left']));text="";spans=[]
        for word in words:
            if text:text+=" "
            start=len(text);text+=word['text'].strip();spans.append((start,len(text),word))
        for match in re.finditer(patterns[caption],text,re.IGNORECASE):
            contributing=[word for left,right,word in spans if right>match.start() and left<match.end()]
            matches.append(([min(int(w['left']) for w in contributing),min(int(w['top']) for w in contributing),
                max(int(w['left'])+int(w['width']) for w in contributing),max(int(w['top'])+int(w['height']) for w in contributing)],contributing))
    if len(matches)>1:raise RuntimeError("Ambiguous source level caption")
    return matches[0][1 if contributing_rows else 0] if matches else None


def source_hud_boxes(tsv,size):
    hp=label_box(clipped_word_tsv(tsv,roi_rectangles(size,"HP")[0]),"HP")
    pause=label_box(clipped_word_tsv(tsv,roi_rectangles(size,"暫停")[0]),"暫停")
    level=None;prefix=None
    for candidate in SOURCE_LEVEL_PREFIXES:
        level=source_level_box(clipped_word_tsv(tsv,roi_rectangles(size,candidate)[0]),candidate)
        if level:prefix=candidate;break
    return {"hpBox":hp,"levelBox":level,"levelPrefix":prefix,"pauseBox":pause,"complete":bool(hp and level and pause)}


def source_skill_box(tsv,size):
    matches=[]
    for caption in SOURCE_SKILL_CAPTIONS:
        box=exact_word_box(clipped_word_tsv(tsv,roi_rectangles(size,caption)[0]),caption)
        if box:matches.append((caption,map_box(box,[0,0],size)))
    if len(matches)>1:raise RuntimeError("Ambiguous source ability-button glyphs; no tap guessed")
    return matches[0] if matches else None


def visible_choice_proof(tsv,captions):
    read_tsv(tsv) # Schema failures cannot be mistaken for an absent card.
    observed=[];chosen=None
    for source_index,caption in enumerate(captions):
        try:box=label_box(tsv,caption)
        except RuntimeError as error:
            if "Ambiguous visible caption" not in str(error):raise
            observed.append({"caption":caption,"sourceIndex":source_index,"status":"AMBIGUOUS_EXCLUDED","nativeBox":None})
            continue
        if box:
            row={"caption":caption,"sourceIndex":source_index,"status":"UNIQUE_VISIBLE","nativeBox":box}
            observed.append(row)
            if chosen is None:chosen=row
    return {"selectionRule":"FIRST_SOURCE_ORDER_CAPTION_WITH_ONE_VISIBLE_TEXT_BBOX_EXCLUDE_AMBIGUOUS_CAPTIONS",
        "observedChoices":observed,"chosen":chosen,"fixedCardCoordinatesUsed":False}


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


def main():
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != "mars-tw/taiwan-train-math"
            or os.environ.get("GITHUB_REF") != "refs/heads/codex/ashes-simulator-recording"):
        raise RuntimeError("Fixed Crack QA branch only")
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    sdk = Path(os.environ["CRACK_SDK"]).resolve()
    if not sdk.is_relative_to(temp) or not os.access("/dev/kvm", os.R_OK | os.W_OK):
        raise RuntimeError("Owned SDK and usable KVM required; no TCG fallback")
    out = Path(os.environ["GITHUB_WORKSPACE"]) / "output/crack-code2-runtime"
    frames = out / "native-frames"
    frames.mkdir(parents=True, exist_ok=True)
    input_dir = temp / "crack-code2-input"
    apk = input_dir / APK_NAME
    provenance = json.loads((input_dir / "fetch-provenance.json").read_text())
    if (apk.stat().st_size != 68463980 or hashlib.sha256(apk.read_bytes()).hexdigest() != APK_SHA
            or provenance.get("assetId") != 632396712 or provenance.get("apkSha256") != APK_SHA
            or provenance.get("releaseId") != 410075088
            or provenance.get("versionCode") != 2
            or provenance.get("rawSourceManifestSha256") != "975871052ae1a04944b009957b09afc0db74ced44bcbcfbd66b48bb3a01cdb0a"):
        raise RuntimeError("Relayed frozen APK/provenance mismatch")
    (out / "fetch-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    adb = str(sdk / "platform-tools/adb")
    emulator = str(sdk / "emulator/emulator")
    run_id = os.environ["GITHUB_RUN_ID"]
    avd = "CrackCode2_" + run_id
    deadline = time.monotonic() + 900
    report = {"schemaVersion": 1, "projectId": "crackveil-vanguard", "status": "PREPARING",
        "runId": run_id, "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"), "physical": False,
        "deviceKind": "OFFICIAL_ANDROID_EMULATOR_KVM", "apkSha256": APK_SHA,
        "versionCode": 2, "rawSourceManifestSha256": "975871052ae1a04944b009957b09afc0db74ced44bcbcfbd66b48bb3a01cdb0a",
        "privateIos2PckContext": "a6676ef12cf8badb262ebdd475db0e6eafb2c74369666f7c8ca56d4d5c1e17d0",
        "differentIosSceneAndConfigResourceCount": 40, "wholeIosPayloadEquivalent": False,
        "gpuRequested": GPU_MODE, "experiment": "EXPLICIT_SUPPORTED_SWANGLE_ENVIRONMENT_COMPATIBILITY_TEST",
        "gameSourceShaderUniformFixClaimed": False, "previousR1CandidateHistoryPreserved": True, "accelRequested": "on",
        "ocrConfiguredMaximumSeconds":60, "ocrChildOmpThreadLimit":1,
        "flowAbsoluteDeadlineSeconds":900,
        "sourceCaptionContract":SOURCE_CAPTION_CONTRACT,
        "automaticRendererFallback": False, "automaticEmulatorRestart": False,
        "bootVerified": False, "installedIdentityVerified": False, "startMenuObserved": False,
        "visibleStartTapped": False, "gameplayHudObserved": False, "movementGestureExecuted": False,
        "pauseResumeObserved": False, "worldMapObserved": False, "mapChoiceTapped": False,
        "mapSelectionNativeVerified": False, "worldMapObservationOnly": True,
        "previousFailedR4RunPreserved": 38204384086,
        "introObserved": False, "contractChoiceTapped": False, "normalSkillTapped": False,
        "normalQuitToLauncherObserved": False,
        "warmRelaunchObserved": False, "sessionControlSmokeCaptured": False,
        "nativeGameplayAccepted": False, "nativeRuntimeReady": False, "allBattlefieldsCompletedVerified": False,
        "gameSourceChanged": False, "gameStateInjected": False, "physicalDeviceRequirementSatisfied": False,
        "realTesterParticipationInferred": False, "storeWrites": 0, "captures": [], "inputs": [],
        "limits": ["Real native emulator frames and normal UI inputs; root visual acceptance remains required",
                   "Control-flow session is not an assertion that all battlefields or boss encounters completed",
                   "Emulator evidence is not physical iPhone/iPad proof or Google human opt-in evidence"]}
    proc = recorder = None
    remote_movie = None
    sequence = 0
    notice_dismissals = {"cold": 0, "warm": 0}

    def save():
        (out / "native-observation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    def command(argv, timeout=20, allow_failure=False):
        if time.monotonic() >= deadline:
            raise FlowDeadlineExceeded("NATIVE_FLOW_DEADLINE_900S_EXCEEDED: owned command")
        result = subprocess.run(argv, capture_output=True, timeout=min(timeout, max(.1, deadline - time.monotonic())))
        if result.returncode and not allow_failure:
            raise RuntimeError("Owned native command failed: " + Path(argv[0]).name + " " + " ".join(argv[1:4]))
        return result

    def device(*args, timeout=20, allow_failure=False):
        return command([adb, "-s", SERIAL, *args], timeout, allow_failure)

    def capture(label, until=None, caption=None):
        nonlocal sequence
        caption_until = deadline if until is None else until
        report["currentObservationPhase"] = label
        sequence += 1
        name = f"{sequence:03d}-{label}.png"
        remaining = caption_budget(caption or label, caption_until, deadline)
        try:
            raw = device("exec-out", "screencap", "-p", timeout=min(20, remaining)).stdout
        except subprocess.TimeoutExpired:
            caption_budget(caption or label, caption_until, deadline)
            raise
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        if image.width < 600 or image.height < 300 or image.width * image.height > 5000000:
            raise RuntimeError("Native viewport unexpectedly small or oversized")
        path = frames / name
        path.write_bytes(raw)
        report["captures"].append({"name": name, "nativeWidth": image.width, "nativeHeight": image.height,
                                   "sha256": hashlib.sha256(raw).hexdigest(), "ocrComplete": False})
        save()
        ocr_argv = ["tesseract", str(path), "stdout", "-l", "chi_tra+eng", "--psm", "11", "tsv"]
        remaining = caption_budget(caption or label, caption_until, deadline)
        ocr_stdout, ocr_stderr, ocr_receipt = bounded_native_ocr(ocr_argv, remaining)
        path.with_suffix(".ocr.stdout.txt").write_bytes(ocr_stdout)
        path.with_suffix(".ocr.stderr.txt").write_bytes(ocr_stderr)
        path.with_suffix(".tsv").write_bytes(ocr_stdout)
        ocr_receipt.update(nativeFrame=name, nativeFrameSha256=hashlib.sha256(raw).hexdigest(),
            argv=ocr_argv, stdoutFile=path.with_suffix(".ocr.stdout.txt").name,
            stderrFile=path.with_suffix(".ocr.stderr.txt").name)
        path.with_suffix(".ocr-receipt.json").write_text(json.dumps(ocr_receipt,indent=2)+"\n")
        report["captures"][-1]["ocrReceipt"] = ocr_receipt
        save()
        caption_budget(caption or label, caption_until, deadline)
        if ocr_receipt["timedOut"]:
            raise RuntimeError("OCR_CHILD_TIMEOUT_OMP1_WITHIN_REMAINING_FLOW_BUDGET: " + name)
        if ocr_receipt["exitCode"] != 0:
            raise RuntimeError("OCR_CHILD_NONZERO_STDERR_PRESERVED: " + name)
        ocr = ocr_stdout.decode("utf-8", "replace")
        text = " ".join(row["text"] for row in read_tsv(ocr)[1] if row["text"])
        report["captures"][-1].update(ocrComplete=True, ocrText=text[:4096])
        save()
        return image, ocr, name

    def scoped_caption(image, tsv, basis, caption, until):
        caption_budget(caption, until, deadline)
        finder = source_level_box if caption in SOURCE_LEVEL_PREFIXES else exact_word_box if caption in SOURCE_SKILL_CAPTIONS else label_box
        native_tsv = clipped_word_tsv(tsv, roi_rectangles(image.size, caption)[0]) if caption in SOURCE_LEVEL_PREFIXES + SOURCE_SKILL_CAPTIONS else tsv
        box = finder(native_tsv, caption)
        if box:
            return map_box(box, [0, 0], image.size), tsv
        def caption_ocr(argv, remaining):
            return bounded_native_ocr(argv, min(remaining, caption_budget(caption, until, deadline)))
        proof = find_caption_roi(frames / basis, caption, caption_budget(caption, until, deadline),
            caption_ocr, finder, frames / "derived-roi")
        report.setdefault("scopedRoiCaptionProof", []).append({"caption":caption,"basisNativeFrame":basis,
            "nativeBox":proof["nativeBox"],"originalSha256":proof["originalSha256"],"trials":proof["trials"],
            "coordinatesRequireRecognizedText":True})
        save()
        caption_budget(caption, until, deadline)
        if proof["nativeBox"]:
            # Add only words that proved this caption. Full ROI TSV/provenance stays
            # in its receipt files; unrelated glyphs cannot become duplicate entities.
            combined = merge_tsv(tsv, proof["nativeCaptionTSV"])
            return proof["nativeBox"], combined
        return None, tsv

    def wait_caption(caption, label, seconds=30):
        until = min(deadline, time.monotonic() + seconds)
        while time.monotonic() < until:
            if proc is not None and proc.poll() is not None:
                raise RuntimeError("Owned emulator exited before visible UI proof")
            image, tsv, name = capture(label, until, caption)
            if caption == "開始出擊":
                launch = "warm" if label.startswith("warm") else "cold"
                if dismiss_systemui_notice(label+"-delayed-notice", image, tsv, name, launch=launch):
                    continue
            box, recognized_tsv = scoped_caption(image, tsv, name, caption, until)
            if box:
                return image, recognized_tsv, name, box
            time.sleep(min(3 if seconds <= 30 else 10, caption_budget(caption, until, deadline)))
        caption_budget(caption, until, deadline)
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
        remote_xml = "/sdcard/CrackCode2_" + run_id + "_notice.xml"
        device("shell", "uiautomator", "dump", remote_xml, timeout=30)
        xml = device("exec-out", "cat", remote_xml).stdout.decode("utf-8", "replace")
        (frames / (Path(basis).stem + ".uiautomator.xml")).write_text(xml)
        notice = system_ui_notice_from_frame(xml, image.width, image.height, tsv, notice_dismissals[launch])
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
        notice_dismissals[launch] += 1
        report["systemUiNoticeDismissals"] = dict(notice_dismissals)
        time.sleep(1)
        capture(label + "-after-dismiss")
        return True

    def tap_observed(image, basis, box, caption, action="tap"):
        box = map_box(box, [0, 0], image.size)
        point = [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2]
        if not (0 <= point[0] < image.width and 0 <= point[1] < image.height):
            raise RuntimeError("Observed caption tap outside native frame")
        report["inputs"].append({"action": action, "caption": caption, "basisNativeFrame": basis,
            "observedTextBox": box, "nativePoint": point})
        save()
        device("shell", "input", "tap", *map(str, point))
        time.sleep(.7)

    def unique_visible_choice(tsv, captions, basis, modal):
        proof = visible_choice_proof(tsv, captions)
        report.setdefault("observedModalChoices", []).append({"basisNativeFrame":basis,"modal":modal,**proof})
        save()
        chosen = proof["chosen"]
        return (chosen["caption"], chosen["nativeBox"]) if chosen else None

    def source_skill(image, tsv, basis, until):
        caption_budget("旋/斬", until, deadline)
        choice = source_skill_box(tsv, image.size)
        if choice:return choice
        for caption in SOURCE_SKILL_CAPTIONS:
            box, context = scoped_caption(image, tsv, basis, caption, until)
            if box:
                choice = source_skill_box(context, image.size)
                if not choice:raise RuntimeError("Derived skill glyph lacks unique native-region proof")
                return choice
        raise RuntimeError("Unique source lower-right 旋/斬 glyph not observed; no tap guessed")

    def hud(label):
        until = min(deadline, time.monotonic() + 60)
        while time.monotonic() < until:
            image, tsv, name = capture(label, until, "HP/Lv.或等級/暫停")
            launch = "warm" if label.startswith("warm") else "cold"
            if dismiss_systemui_notice(label+"-delayed-notice", image, tsv, name, launch=launch):
                continue
            if launch == "warm" and label_box(tsv, "開始出擊"):
                tap_observed(image, name, label_box(tsv,"開始出擊"),"開始出擊","warm_visible_start")
                report["warmReturnScreen"] = "LATE_VISIBLE_TITLE"
                continue
            if label_box(tsv, "直接出擊"):
                report["introObserved"] = True
                tap_observed(image, name, label_box(tsv, "直接出擊"), "直接出擊", "normal_intro_dismiss")
                continue
            if label_box(tsv, "選擇裂隙契約"):
                choice = unique_visible_choice(tsv, ["血稅", "金饑", "靜幕", "精英信標", "玻璃磁界", "單線協定"], name, "contract")
                if not choice:
                    raise RuntimeError("Contract modal visible but no unique known card caption; no card guessed")
                tap_observed(image, name, choice[1], choice[0], "normal_contract_card")
                report["contractChoiceTapped"] = True
                confirm_image, confirm_tsv, confirm_name = capture(label + "-contract-after-first-tap")
                confirm = label_box(confirm_tsv, "再次點擊確認")
                if confirm:
                    tap_observed(confirm_image, confirm_name, confirm, "再次點擊確認", "normal_contract_confirmation")
                continue
            if label_box(tsv, "選擇升級") or label_box(tsv, "再點高亮卡確認"):
                choice = unique_visible_choice(tsv, SOURCE_OPTION_CAPTIONS, name, "upgrade")
                if not choice:
                    raise RuntimeError("Upgrade modal visible but no unique source-defined card caption; no card guessed")
                tap_observed(image, name, choice[1], choice[0], "normal_upgrade_card")
                confirm_image, confirm_tsv, confirm_name = capture(label + "-upgrade-after-first-tap")
                if label_box(confirm_tsv, "再點高亮卡確認"):
                    again = label_box(confirm_tsv, choice[0])
                    if not again:
                        raise RuntimeError("Actual selected upgrade card no longer uniquely visible; no repeated tap")
                    tap_observed(confirm_image, confirm_name, again, choice[0], "normal_upgrade_confirmation")
                continue
            if label_box(tsv, "回主選單"):
                raise RuntimeError("Normal game-over occurred before required control smoke was complete")
            hp_box, tsv = scoped_caption(image, tsv, name, "HP", until)
            level_box = None
            for level_prefix in SOURCE_LEVEL_PREFIXES:
                level_box, tsv = scoped_caption(image, tsv, name, level_prefix, until)
                if level_box:break
            pause_box, tsv = scoped_caption(image, tsv, name, "暫停", until)
            if hp_box and level_box and pause_box:
                report.setdefault("sourceHudCaptionProof", []).append({"basisNativeFrame":name,
                    "hpBox":hp_box,"levelPrefix":level_prefix,"levelBox":level_box,"pauseBox":pause_box})
                save()
                return image, tsv, name
            time.sleep(min(1, caption_budget("HP/Lv.或等級/暫停", until, deadline)))
        caption_budget("HP/Lv.或等級/暫停", until, deadline)
        raise RuntimeError("Active native HP/level/pause HUD not observed within bound")

    def foreground_component():
        text = device("shell", "dumpsys", "activity", "activities").stdout.decode("utf-8", "replace")
        matches = re.findall(r"(?:mResumedActivity|topResumedActivity).*?\s([A-Za-z0-9_.]+/[A-Za-z0-9_.$]+)\s", text)
        if not matches or len(set(matches)) != 1:
            raise RuntimeError("Unique actual resumed activity unavailable")
        return matches[0]

    def movement(label):
        image, tsv, basis = hud(label + "-before")
        values, verified = locate_visible_joystick(image)
        circle = verified["circle"]
        x, y, radius = circle
        gesture = [round(x), round(y), round(x + radius * .72), round(y), 1800]
        report["inputs"].append({"action": "joystick_swipe", "basisNativeFrame": basis,
            "observedCircleCandidates": values, "selectedCircle": circle,
            "centerKnobBrightFraction": verified["knobBrightFraction"], "nativeGesture": gesture})
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
        if avd_home != temp / "crack-code2-avds" or user_home != temp / "crack-code2-user":
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
        report.update(actualGuestAbi64=guest_abi, actualGuestNativeBridge=bridge)
        (out / "actual-guest-abi-properties.json").write_text(json.dumps({"abi64":guest_abi,"nativeBridge":bridge},indent=2)+"\n")
        save()
        if "arm64-v8a" not in guest_abi.split(",") or bridge != "libndk_translation.so":
            raise RuntimeError("Actual guest ARM64 bridge absent; no injection allowed")
        report.update(bootVerified=True, actualGuestAbi64=guest_abi, actualGuestNativeBridge=bridge)
        actual_boot_log = (out / "owned-emulator.log").read_text(encoding="utf-8", errors="replace")
        report["actualSwangleGlesSelectionVerified"] = verify_swangle_boot_selection(actual_boot_log)
        report["actualGraphicsModeLines"] = [line for line in actual_boot_log.splitlines()
            if any(key in line for key in ["emuglConfig_init", "Graphics Adapter", "Graphics API Version"])]
        save()
        device("shell", "input", "keyevent", "82")
        device("install", "-r", str(apk), timeout=90)
        package = device("shell", "dumpsys", "package", PACKAGE).stdout.decode()
        if not re.search(r"versionCode=2\b", package) or "versionName=1.0.0" not in package:
            raise RuntimeError("Installed fixed package/version differs")
        resolved = device("shell", "cmd", "package", "resolve-activity", "--brief", PACKAGE).stdout.decode().strip().splitlines()[-1]
        if resolved != ALIAS:
            raise RuntimeError("Actual MAIN launcher alias differs; no non-exported activity attempted")
        report.update(installedIdentityVerified=True, resolvedActivity=resolved)
        device("logcat", "-c")
        start = device("shell", "am", "start", "-W", "-n", ALIAS, timeout=45).stdout.decode()
        report["actualStartCommandOutput"] = start
        dismiss_systemui_notice("cold-systemui-notice")
        wait_caption("開始出擊", "cold-title-wait", seconds=360)
        report["startMenuObserved"] = True
        save()
        remote_movie = "/sdcard/CrackCode2_" + run_id + ".mp4"
        recorder = subprocess.Popen([adb, "-s", SERIAL, "shell", "screenrecord", "--time-limit", "180", remote_movie],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tap_caption("世界地圖", "observed-world-map")
        image, tsv, basis, map_box_observed = wait_caption("關卡出擊", "world-map-ready")
        report["worldMapObserved"] = True
        report.update(worldMapEvidenceFrame=basis, worldMapEvidenceCaption="關卡出擊",
            worldMapEvidenceNativeBox=map_box_observed, mapChoiceTapped=False, mapSelectionNativeVerified=False,
            mapChoiceSkippedReason="Observed world map only; multiple visible map cards are outside this control-smoke diagnostic")
        save()
        tap_caption("返回", "observed-map-return")
        wait_caption("開始出擊", "after-map-main-menu")
        tap_caption("開始出擊", "observed-start")
        report["visibleStartTapped"] = True
        hud("after-visible-start")
        report["gameplayHudObserved"] = True
        image, tsv, basis = hud("skill-ready")
        skill_caption, skill = source_skill(image, tsv, basis, min(deadline, time.monotonic()+30))
        tap_observed(image, basis, skill, skill_caption, "normal_leader_skill")
        report["normalSkillSourceCaption"] = skill_caption
        report["normalSkillTapped"] = True
        capture("after-normal-skill")
        movement("movement-one")
        tap_caption("暫停", "observed-pause")
        image, tsv, basis, _ = wait_caption("繼續", "pause-menu")
        if not label_box(tsv, "設定"):
            raise RuntimeError("Resume text without actual settings pause overlay")
        tap_caption("繼續", "observed-resume")
        hud("after-resume")
        report["pauseResumeObserved"] = True
        before_pid = device("shell", "pidof", PACKAGE, allow_failure=True).stdout.decode().strip()
        before_component = foreground_component()
        if not before_component.startswith(PACKAGE+"/"):
            raise RuntimeError("Game not foreground before normal Android Back")
        report["inputs"].append({"action":"normal_android_back","keyCode":4,"priorForeground":before_component})
        save()
        device("shell", "input", "keyevent", "4")
        time.sleep(1)
        capture("normal-back-result")
        after_component = foreground_component()
        if after_component.startswith(PACKAGE+"/") or not any(x in after_component for x in ["nexuslauncher", "launcher3", "launcher"]):
            raise RuntimeError("Normal Back did not visibly exit to actual launcher; no force-stop substitute")
        report.update(normalQuitToLauncherObserved=True, normalBackForeground=after_component,
            processPidBeforeBack=before_pid, processPidAfterBack=device("shell","pidof",PACKAGE,allow_failure=True).stdout.decode().strip())
        device("shell", "am", "start", "-W", "-n", ALIAS, timeout=45)
        dismiss_systemui_notice("warm-systemui-notice", launch="warm")
        image, tsv, basis = capture("warm-normal-return")
        if label_box(tsv, "開始出擊"):
            report["warmReturnScreen"] = "TITLE"
            tap_caption("開始出擊", "warm-visible-start")
        else:
            report["warmReturnScreen"] = "ACTUAL_RESUMED_GAMEPLAY_REQUIRES_HUD"
        hud("warm-gameplay")
        report["warmRelaunchObserved"] = True
        report["sessionControlSmokeCaptured"] = True
        report["status"] = "NATIVE_CONTROL_FLOW_CAPTURED_PENDING_ROOT_VISUAL_GAMEPLAY_ACCEPTANCE"
        if recorder is not None:
            recorder.wait(timeout=185)
            movie = out / "CrackCode2-native-emulator-control-flow.mp4"
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
            if report["status"] == "FAILED_NATIVE_OBSERVATION":
                try:
                    shot = subprocess.run([adb,"-s",SERIAL,"exec-out","screencap","-p"],capture_output=True,timeout=15)
                    if shot.returncode==0 and shot.stdout.startswith(b"\x89PNG"):
                        (frames/"failure-final-native.png").write_bytes(shot.stdout)
                        report["failureFinalFrameSha256"]=hashlib.sha256(shot.stdout).hexdigest()
                except Exception as error:
                    report["failureFrameErrorType"] = type(error).__name__
            try:
                log = subprocess.run([adb,"-s",SERIAL,"logcat","-d","-v","threadtime"],capture_output=True,timeout=20).stdout
                (out/"owned-guest-logcat.txt").write_bytes(log[:4*1024*1024])
                report["guestLogcatTruncated"] = len(log)>4*1024*1024
            except Exception as error:
                report["logcatPreservationErrorType"] = type(error).__name__
            if recorder is not None and "nativeMovie" not in report:
                try:
                    recorder.wait(timeout=185)
                    movie=out/"CrackCode2-native-emulator-control-flow.mp4"
                    result=subprocess.run([adb,"-s",SERIAL,"pull",remote_movie,str(movie)],capture_output=True,timeout=45)
                    if result.returncode==0 and movie.is_file() and movie.stat().st_size>0:
                        report["nativeMovie"]={"file":movie.name,"bytes":movie.stat().st_size,
                            "sha256":hashlib.sha256(movie.read_bytes()).hexdigest(),"physical":False,
                            "scenarioFailed":report["status"]=="FAILED_NATIVE_OBSERVATION"}
                except Exception as error:
                    if recorder.poll() is None:
                        recorder.terminate()
                    report["nativeMovieFinalizationErrorType"]=type(error).__name__
            try:
                if proc.poll() is None:
                    actual=subprocess.run([adb,"-s",SERIAL,"emu","avd","name"],capture_output=True,timeout=10).stdout.decode().splitlines()
                    if actual and actual[0]==avd:
                        subprocess.run([adb,"-s",SERIAL,"emu","kill"],capture_output=True,timeout=10)
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid,signal.SIGTERM)  # Only the Popen child session created here.
                        proc.wait(timeout=10)
                report["ownedEmulatorStopped"]=proc.poll() is not None
                report["ownedEmulatorExitCode"]=proc.poll()
            except Exception as error:
                report["cleanupErrorType"]=type(error).__name__
            save()



if __name__ == "__main__":
    main()
