"""One pinned build11 Android KVM native observation on the dedicated QA branch.

This driver has no network or publishing operations. It uses only normal adb UI
input against the emulator it creates, and keeps original PNG, video and logcat
evidence. Native readiness is a narrow runtime finding, not gameplay acceptance.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import socket
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


REPOSITORY = "mars-tw/taiwan-train-math"
BRANCH = "codex/seven-build11-r13-native-qa"
RELEASE_TAG = "seven-build11-r13-kvm-qa-20261013-690a46a0-6b82c3d5591f"
PACKAGE = "tw.mars.sevendistrictreckoning"
ALIAS = PACKAGE + "/com.godot.game.GodotAppLauncher"
APK_NAME = "seven-district-reckoning-1.0.0-build11-test-signed.apk"
APK_BYTES = 90_561_618
APK_SHA = "690a46a0447c322f9c096f8d83fe108e354709a50fc26d0cb2b592923c951823"
CERT_SHA = "1dd3cc96a02e4555e8d91a42d749a019ee5c4781d4d7510947ae48c865e21110"
SOURCE_PINS = {
    "baseOptimizationPatchSha256": "e717397651c82fc4a3790414ebe06d1b1a2d040ae44b1c005ee5c83320a9a995",
    "titleCtaPatchSha256": "4fb0cca3b9f20915f09cc70935f1a2956eb8e3c5dc5b751d5ae04631989b0200",
    "sourceBindSha256": "1015dce084c55afbd5f7cb301b3fd9b998e2056df62b3a05ac9fc4ba8c084037",
}
TOUCH_LAYOUT_SOURCE_SHA = "abee39b9e5cd6ab3891230bcd57e802377c17094355e131db543a9794d7db1a9"
DEVICE_PROFILES_SOURCE_SHA = "31e4758a205430b66fcbcb034736de07adb3febc65d4e06c51fe5d969dc02090"
SERIAL = "emulator-5580"
AVD_PORT = 5580
GPU_MODE = "swangle"
SYSTEM_IMAGE = "system-images;android-36;google_apis;x86_64"
FLOW_SECONDS = 1_500
TITLE_SECONDS = 420
WORLD_SECONDS = 900
HUD_SECONDS = 420
OCR_SECONDS = 60
MAX_UI_DUMPS = 2
MAX_SYSTEMUI_DISMISSALS = 2
MAX_LOGCAT_BYTES = 12 * 1024 * 1024


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    hash_ = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hash_.update(block)
    return hash_.hexdigest()


def retained_logcat(raw: bytes) -> tuple[bytes, bool]:
    """Keep a bounded complete-line tail; parsers must use these same bytes."""
    if len(raw) <= MAX_LOGCAT_BYTES:
        return raw, False
    tail = raw[-MAX_LOGCAT_BYTES:]
    first_newline = tail.find(b"\n")
    return (tail[first_newline + 1:] if first_newline >= 0 else b""), True


def read_small_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise RuntimeError("Missing, linked or oversized pinned JSON: " + path.name)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Pinned JSON must be an object: " + path.name)
    return value


def verify_manifest(manifest: dict) -> None:
    exact = {
        "projectId": "seven-district-reckoning", "repository": REPOSITORY,
        "branch": BRANCH, "appId": PACKAGE, "versionName": "1.0.0",
        "versionCode": 11,
    }
    for key, value in exact.items():
        if manifest.get(key) != value:
            raise RuntimeError("Prepared manifest mismatch: " + key)
    apk = manifest.get("apk")
    if not isinstance(apk, dict) or any(apk.get(k) != v for k, v in {
        "file": APK_NAME, "bytes": APK_BYTES, "sha256": APK_SHA,
        "certificateSha256": CERT_SHA,
    }.items()):
        raise RuntimeError("Prepared manifest APK identity mismatch")
    source = manifest.get("source")
    if not isinstance(source, dict) or any(source.get(k) != v for k, v in SOURCE_PINS.items()):
        raise RuntimeError("Prepared manifest source identity mismatch")
    release = manifest.get("release")
    if not isinstance(release, dict) or release.get("tag") != RELEASE_TAG or release.get("draft") is not True:
        raise RuntimeError("Prepared manifest draft release identity mismatch")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict) or any(runtime.get(k) != v for k, v in {
        "apiLevel": 36, "abi": "x86_64,arm64-v8a",
        "bridge": "libndk_translation.so", "gpu": GPU_MODE,
        "image": SYSTEM_IMAGE, "imageRevision": 7,
        "emulatorVersion": "37.2.12", "buildToolsVersion": "36.1.0",
    }.items()):
        raise RuntimeError("Prepared manifest native runtime pins mismatch")


def verify_provenance(provenance: dict, manifest: dict) -> None:
    exact = {
        "projectId": "seven-district-reckoning", "repository": REPOSITORY,
        "branch": BRANCH, "apkFile": APK_NAME,
        "apkSha256": APK_SHA, "apkBytes": APK_BYTES,
        "versionCode": 11, "versionName": "1.0.0", "appId": PACKAGE,
        "certificateSha256": CERT_SHA, "releaseTag": RELEASE_TAG,
        "releaseDraft": True,
        **SOURCE_PINS,
    }
    for key, value in exact.items():
        if provenance.get(key) != value:
            raise RuntimeError("Fetched APK provenance mismatch: " + key)
    release = manifest["release"]
    for key in ("releaseId", "assetId"):
        actual = provenance.get(key)
        if type(actual) is not int or actual <= 0:
            raise RuntimeError("Missing positive fetched " + key)
        if release.get(key) is not None and release[key] != actual:
            raise RuntimeError("Fetched " + key + " differs from manifest")


def exact_environment() -> tuple[Path, Path, Path, Path, Path, Path]:
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_EVENT_NAME") != "push"
            or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
            or os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH):
        raise RuntimeError("Dedicated GitHub Actions push branch only")
    if sys.platform != "linux" or platform.freedesktop_os_release().get("ID") != "ubuntu" or platform.freedesktop_os_release().get("VERSION_ID") != "24.04":
        raise RuntimeError("Ubuntu 24.04 host only")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run_id):
        raise RuntimeError("Invalid GitHub Actions run id")
    raw_temp = os.environ.get("RUNNER_TEMP", "")
    raw_workspace = os.environ.get("GITHUB_WORKSPACE", "")
    if not os.path.isabs(raw_temp) or not os.path.isabs(raw_workspace):
        raise RuntimeError("Runner temp and workspace must be absolute")
    temp = Path(raw_temp).resolve()
    workspace = Path(raw_workspace).resolve()
    exact = {
        "SEVEN_SDK": temp / "seven-build11-r13-sdk",
        "SEVEN_APK": temp / "seven-build11-r13-input" / APK_NAME,
        "SEVEN_OUTPUT": workspace / "output" / "seven-build11-r13-kvm",
        "ANDROID_AVD_HOME": temp / "seven-build11-r13-avds",
        "ANDROID_USER_HOME": temp / "seven-build11-r13-user",
    }
    values = {}
    for key, expected in exact.items():
        raw = os.environ.get(key, "")
        if not os.path.isabs(raw) or Path(raw).resolve() != expected:
            raise RuntimeError("Unexpected owned runner path: " + key)
        values[key] = expected
    if not values["SEVEN_OUTPUT"].is_relative_to(workspace):
        raise RuntimeError("Evidence output leaves GitHub workspace")
    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        raise RuntimeError("Readable and writable /dev/kvm required; no TCG fallback")
    return (temp, workspace, values["SEVEN_SDK"], values["SEVEN_APK"],
            values["SEVEN_OUTPUT"], values["ANDROID_AVD_HOME"])


def normalized(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9\u3400-\u9fff]", "", value).casefold()


def label_box(tsv: str, caption: str) -> list[int] | None:
    """Return exactly one OCR line occurrence; ambiguity never produces input."""
    lines: dict[tuple[str, ...], list[dict]] = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row.get("level") != "5" or not normalized(row.get("text", "")):
            continue
        try:
            if float(row["conf"]) < 25:
                continue
            key = tuple(row[k] for k in ("page_num", "block_num", "par_num", "line_num"))
            lines.setdefault(key, []).append(row)
        except (ValueError, KeyError):
            continue
    matches = []
    wanted = normalized(caption)
    for words in lines.values():
        words.sort(key=lambda word: int(word["left"]))
        line = ""
        spans = []
        for word in words:
            start = len(line)
            line += normalized(word["text"])
            spans.append((start, len(line), word))
        first = line.find(wanted)
        if first < 0:
            continue
        if line.find(wanted, first + 1) >= 0:
            raise RuntimeError("Ambiguous repeated caption within OCR line: " + caption)
        contributors = [word for start, end, word in spans if end > first and start < first + len(wanted)]
        left = min(int(word["left"]) for word in contributors)
        top = min(int(word["top"]) for word in contributors)
        right = max(int(word["left"]) + int(word["width"]) for word in contributors)
        bottom = max(int(word["top"]) + int(word["height"]) for word in contributors)
        matches.append([left, top, right, bottom])
    if len(matches) > 1:
        raise RuntimeError("Ambiguous visible OCR caption: " + caption)
    return matches[0] if matches else None


def valid_uiautomator_xml(stdout: bytes, exit_code: int) -> str | None:
    if exit_code != 0 or not stdout or len(stdout) > 512 * 1024:
        return None
    try:
        xml = stdout.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        return None
    if not (xml.startswith("<?xml") or xml.startswith("<hierarchy")) or "<!DOCTYPE" in xml or "<!ENTITY" in xml:
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    return xml if root.tag == "hierarchy" else None


def xml_bounds(node: ET.Element, width: int, height: int) -> list[int] | None:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
    if not match:
        return None
    box = list(map(int, match.groups()))
    return box if 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height else None


def systemui_notice_from_frame(xml: str, tsv: str, width: int, height: int) -> dict | None:
    """Match an enabled SystemUI Got it within the panel containing both OCR lines."""
    title = label_box(tsv, "Viewing full screen")
    instruction = label_box(tsv, "To exit, swipe down from the top of your screen")
    if not title or not instruction:
        return None
    root = ET.fromstring(xml)
    parents = {child: parent for parent in root.iter() for child in parent}
    candidates = [node for node in root.iter("node")
                  if node.get("package") == "com.android.systemui"
                  and node.get("text") == "Got it"
                  and node.get("enabled", "true") == "true"
                  and node.get("visible-to-user", "true") == "true"]
    if len(candidates) != 1:
        return None
    button = xml_bounds(candidates[0], width, height)
    if not button:
        return None
    parent = parents.get(candidates[0])
    panels = []
    while parent is not None:
        if parent.get("package") == "com.android.systemui":
            box = xml_bounds(parent, width, height)
            if box and all(box[0] <= sub[0] < sub[2] <= box[2] and box[1] <= sub[1] < sub[3] <= box[3]
                           for sub in (title, instruction, button)):
                panels.append(box)
        parent = parents.get(parent)
    if not panels:
        return None
    panel = min(panels, key=lambda box: (box[2] - box[0]) * (box[3] - box[1]))
    return {"package": "com.android.systemui", "buttonBounds": button,
            "panelBounds": panel, "titleOCRBounds": title, "instructionOCRBounds": instruction}


def world_ready_events(log: str) -> list[dict]:
    events = []
    for line in log.splitlines():
        marker = line.find("SEVEN_STARTUP ")
        if marker < 0:
            continue
        try:
            sample = json.loads(line[marker + len("SEVEN_STARTUP "):])
        except json.JSONDecodeError:
            continue
        if (isinstance(sample, dict) and sample.get("event") == "complete"
                and sample.get("phase") == "world_ready" and sample.get("ready") is True
                and type(sample.get("render_frames_drawn")) is int
                and sample["render_frames_drawn"] >= 2
                and sample.get("draw_counter_available") is True
                and sample.get("owner_visible_in_tree") is True):
            events.append(sample)
    return events


def post_start_emulator_fps(log: str, start_epoch: float) -> dict:
    """Diagnostic Godot frame-count slope after the visible Start tap only."""
    samples = []
    for line in log.splitlines():
        match = re.match(r"^\s*(\d{10}(?:\.\d+)?)\s+", line)
        marker = line.find("SEVEN_STARTUP ")
        if not match or marker < 0 or float(match.group(1)) < start_epoch:
            continue
        try:
            sample = json.loads(line[marker + len("SEVEN_STARTUP "):])
        except json.JSONDecodeError:
            continue
        if (isinstance(sample, dict) and sample.get("owner_visible_in_tree") is True
                and sample.get("loading_layer_visible") is False
                and type(sample.get("render_frames_drawn")) is int
                and type(sample.get("elapsed_ms")) in (int, float)):
            samples.append((float(match.group(1)), float(sample["elapsed_ms"]),
                            sample["render_frames_drawn"], str(sample.get("phase", ""))))
    samples.sort()
    intervals = []
    for before, after in zip(samples, samples[1:]):
        elapsed_ms = after[1] - before[1]
        frame_delta = after[2] - before[2]
        # Several phase marks can happen within the same rendered frame. Their
        # near-zero intervals are not a sustained frame-cadence measurement.
        if elapsed_ms >= 250 and frame_delta >= 0:
            intervals.append(frame_delta * 1000.0 / elapsed_ms)
    sorted_fps = sorted(intervals)
    p10 = sorted_fps[max(0, int((len(sorted_fps) - 1) * .10))] if sorted_fps else None
    return {
        "source": "SEVEN_STARTUP render_frames_drawn deltas divided by elapsed_ms deltas",
        "filter": "logcat epoch >= visible Start tap; owner 3D visible; loading layer hidden",
        "minimumIntervalMilliseconds": 250,
        "postTapVisible3DSampleCount": len(samples), "intervalCount": len(intervals),
        "medianFps": round(statistics.median(intervals), 3) if intervals else None,
        "p10Fps": round(p10, 3) if p10 is not None else None,
        "firstSampleEpoch": samples[0][0] if samples else None,
        "lastSampleEpoch": samples[-1][0] if samples else None,
        "phases": sorted({sample[3] for sample in samples}),
        "deviceKind": "OFFICIAL_ANDROID_EMULATOR_KVM", "gpu": GPU_MODE,
        "arm64Bridge": "libndk_translation.so", "physicalFpsClaim": False,
        "gameplayAcceptanceByFpsAlone": False,
    }


def verify_wm_720(text: str) -> dict:
    physical = re.findall(r"^Physical size:\s*(\d+)x(\d+)\s*$", text, re.M)
    override = re.findall(r"^Override size:\s*(\d+)x(\d+)\s*$", text, re.M)
    if len(physical) != 1 or override != [("720", "1280")]:
        raise RuntimeError("Owned wm 720x1280 override not proven")
    return {"physical": list(map(int, physical[0])), "override": [720, 1280],
            "expectedLandscapeNativePNG": [1280, 720]}


def verify_wm_density_320(text: str) -> dict:
    physical = re.findall(r"^Physical density:\s*(\d+)\s*$", text, re.M)
    override = re.findall(r"^Override density:\s*(\d+)\s*$", text, re.M)
    if len(physical) != 1 or override != ["320"] or int(physical[0]) <= 0:
        raise RuntimeError("Owned wm density 320 override not proven")
    return {"physicalDpi": int(physical[0]), "overrideDpi": 320}


def exact_app_foreground_evidence(dumpsys: str) -> bool:
    """Accept direct current focus or conservative API36 foreground evidence."""
    top_display = re.findall(r"^[ \t]*mTopFocusedDisplayId\b[^\r\n]*$", dumpsys, re.M)
    valid_top_display = (len(top_display) == 1 and re.fullmatch(
        r"[ \t]*mTopFocusedDisplayId[ \t]*=[ \t]*0[ \t]*", top_display[0]) is not None)
    if top_display and not valid_top_display:
        return False
    focus_lines = re.findall(r"^[ \t]*mCurrentFocus\b[^\r\n]*$", dumpsys, re.M)
    if focus_lines:
        return (len(focus_lines) == 1 and re.fullmatch(
            r"[ \t]*mCurrentFocus[ \t]*=[ \t]*Window\{[0-9a-fA-F]+[ \t]+u\d+[ \t]+"
            + re.escape(PACKAGE) + r"/[^}\s]+\}[ \t]*", focus_lines[0]) is not None)

    # API36's `dumpsys window windows` may omit mCurrentFocus altogether.
    # Require a unique drawn, unobscured app window and both IME targets to
    # identify that same Window token. Reject any competing visible window.
    if not valid_top_display:
        return False
    footer = re.search(r"^  mGlobalConfiguration=", dumpsys, re.M)
    if footer is None:
        return False
    window_section = dumpsys[:footer.start()]
    headers = list(re.finditer(
        r"^\s*Window #\d+ Window\{(?P<token>[0-9a-fA-F]+) "
        r"u(?P<user>\d+) (?P<component>[^}]+)\}:", window_section, re.M))
    windows = [(match, window_section[match.end():headers[index + 1].start()
                                       if index + 1 < len(headers) else len(window_section)])
               for index, match in enumerate(headers)]
    app = [(match, body) for match, body in windows
           if match.group("component") == ALIAS]
    if len(app) != 1:
        return False
    match, body = app[0]
    required = (
        r"^\s*mDisplayId=0(?:\s|$)",
        r"^\s*mOwnerUid=\d+\b[^\n]*\bpackage=" + re.escape(PACKAGE) + r"(?:\s|$)",
        r"^\s*mViewVisibility=0x0\b[^\n]*\bmObscured=false\b",
        r"^\s*mHasSurface=true\b[^\n]*\bisReadyForDisplay\(\)=true\b",
        r"^\s*Surface:\s+shown=true\b",
        r"^\s*isOnScreen=true\b",
        r"^\s*isVisible=true\b",
    )
    unique_fields = (
        r"^\s*mDisplayId=", r"^\s*mOwnerUid=", r"^\s*mViewVisibility=",
        r"^\s*mHasSurface=", r"^\s*Surface:", r"^\s*isOnScreen=",
        r"^\s*isVisible=",
    )
    if (not all(len(re.findall(pattern, body, re.M)) == 1 for pattern in unique_fields)
            or not all(re.search(pattern, body, re.M) for pattern in required)):
        return False
    identity = ("Window{" + match.group("token") + " u" + match.group("user")
                + " " + ALIAS + "}")
    for target in ("imeInputTarget", "imeControlTarget"):
        lines = re.findall(r"^\s*" + target + r" in display# 0 (Window\{[^}]+\})\s*$",
                           dumpsys, re.M)
        if lines != [identity]:
            return False
    for other, other_body in windows:
        if other is match:
            continue
        if (re.search(r"^\s*mDisplayId=0(?:\s|$)", other_body, re.M)
                and re.search(r"^\s*isOnScreen=true\b", other_body, re.M)
                and re.search(r"^\s*isVisible=true\b", other_body, re.M)):
            return False
    return True


def verify_avd_registry(ini: Path, data: Path, name: str, listing: str, temp: Path) -> dict:
    if (ini.is_symlink() or data.is_symlink() or not ini.resolve().is_relative_to(temp)
            or not data.resolve().is_relative_to(temp) or not ini.is_file() or not data.is_dir()):
        raise RuntimeError("Owned AVD registry/data is missing or leaves runner temp")
    pairs = {}
    for line in ini.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if key in pairs:
                raise RuntimeError("Duplicate AVD registry property")
            pairs[key] = value
    if not pairs.get("path") or Path(pairs["path"]).resolve() != data.resolve():
        raise RuntimeError("AVD registry points outside owned data path")
    if [row.strip() for row in listing.splitlines() if row.strip()] != [name]:
        raise RuntimeError("Emulator does not discover exactly the owned AVD")
    return {"registry": str(ini), "data": str(data), "listedNames": [name],
            "properties": pairs, "verified": True}


def read_properties(path: Path) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("Missing pinned SDK source.properties: " + str(path))
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def self_test() -> None:
    """Hardware-free guard tests; run with --self-test on any Python host."""
    tsv = "level\tpage_num\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    tsv += "5\t1\t1\t1\t1\t20\t40\t20\t12\t95\t開始\n"
    tsv += "5\t1\t1\t1\t1\t42\t40\t30\t12\t95\t新遊戲\n"
    assert label_box(tsv, "開始新遊戲") == [20, 40, 72, 52]
    duplicated = tsv + "5\t1\t2\t1\t1\t20\t70\t52\t12\t95\t開始新遊戲\n"
    try:
        label_box(duplicated, "開始新遊戲")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Duplicate OCR caption accepted")
    sample = {"event": "complete", "phase": "world_ready", "ready": True,
              "render_frames_drawn": 3, "draw_counter_available": True,
              "owner_visible_in_tree": True}
    assert len(world_ready_events("I/Godot: SEVEN_STARTUP " + json.dumps(sample))) == 1
    sample["owner_visible_in_tree"] = False
    assert not world_ready_events("I/Godot: SEVEN_STARTUP " + json.dumps(sample))
    fps_a = {**sample, "owner_visible_in_tree": True, "loading_layer_visible": False,
             "render_frames_drawn": 100, "elapsed_ms": 1000}
    fps_b = {**fps_a, "render_frames_drawn": 130, "elapsed_ms": 1500}
    fps_log = "1000000000.000 I Godot: SEVEN_STARTUP " + json.dumps(fps_a) + "\n"
    fps_log += "1000000000.500 I Godot: SEVEN_STARTUP " + json.dumps(fps_b)
    assert post_start_emulator_fps(fps_log, 1000000000.0)["medianFps"] == 60.0
    assert post_start_emulator_fps(fps_log, 1000000000.1)["intervalCount"] == 0
    assert retained_logcat(b"one\ntwo\n") == (b"one\ntwo\n", False)
    xml = '<hierarchy><node package="com.android.systemui" bounds="[0,0][200,100]"><node package="com.android.systemui" text="Got it" bounds="[140,60][190,90]"/></node></hierarchy>'
    assert valid_uiautomator_xml(xml.encode(), 0) == xml
    assert valid_uiautomator_xml(b"warning\n" + xml.encode(), 0) is None
    assert valid_uiautomator_xml(b"<!DOCTYPE foo>" + xml.encode(), 0) is None
    notice_tsv = "level\tpage_num\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    notice_tsv += "5\t1\t1\t1\t1\t10\t10\t100\t12\t95\tViewing full screen\n"
    notice_tsv += "5\t1\t1\t1\t2\t10\t30\t125\t12\t95\tTo exit, swipe down from the top of your screen\n"
    assert systemui_notice_from_frame(xml, notice_tsv, 200, 100)["buttonBounds"] == [140, 60, 190, 90]
    wrong_owner = xml.replace("com.android.systemui", "com.example.app")
    assert systemui_notice_from_frame(wrong_owner, notice_tsv, 200, 100) is None
    assert verify_wm_720("Physical size: 1080x1920\nOverride size: 720x1280\n")["override"] == [720, 1280]
    assert verify_wm_density_320("Physical density: 420\nOverride density: 320\n")["overrideDpi"] == 320
    assert exact_app_foreground_evidence("  mCurrentFocus=Window{42 u0 " + ALIAS + "}\n")
    assert not exact_app_foreground_evidence("  mCurrentFocus=Window{42 u0 tw.mars.sevendistrictreckoning.fake/X}\n")
    assert not exact_app_foreground_evidence("  mCurrentFocus=Window{42 u0 com.example.other/.Activity} " + ALIAS + "\n")
    fixture = (Path(__file__).resolve().parent / "fixtures" /
               "api36-build11-title-foreground.txt").read_text(encoding="utf-8")
    assert "mCurrentFocus" not in fixture
    assert exact_app_foreground_evidence(fixture)
    assert not exact_app_foreground_evidence(fixture + "\n  mCurrentFocus=Window{42 u0 com.example.other/.Activity}\n")
    assert not exact_app_foreground_evidence(fixture + "\n  mCurrentFocus: Window{42 u0 com.example.other/.Activity}\n")
    assert fixture.count("mTopFocusedDisplayId=0") == 1
    assert not exact_app_foreground_evidence(fixture.replace("mTopFocusedDisplayId=0",
                                                     "mTopFocusedDisplayId=1"))
    assert not exact_app_foreground_evidence(fixture + "\n  mCurrentFocus=Window{42 u0 " + ALIAS + "}\n"
                                     + "  mTopFocusedDisplayId=1\n")
    app_start = fixture.index("  Window #8 Window{b0ee4e2 u0 " + ALIAS + "}:")
    app_end = fixture.index("  Window #9 Window{", app_start)

    def mutate_app(old: str, new: str) -> str:
        app_block = fixture[app_start:app_end]
        assert app_block.count(old) == 1
        return fixture[:app_start] + app_block.replace(old, new) + fixture[app_end:]

    assert not exact_app_foreground_evidence(mutate_app("mHasSurface=true isReadyForDisplay()=true",
                                                "mHasSurface=false isReadyForDisplay()=true"))
    assert not exact_app_foreground_evidence(mutate_app("Surface: shown=true", "Surface: shown=false"))
    assert not exact_app_foreground_evidence(mutate_app("isVisible=true", "isVisible=false"))
    assert not exact_app_foreground_evidence(mutate_app("isVisible=true",
        "isVisible=false\n    isVisible=true"))
    assert not exact_app_foreground_evidence(mutate_app("mHasSurface=true isReadyForDisplay()=true",
        "mHasSurface=false isReadyForDisplay()=false\n    mHasSurface=true isReadyForDisplay()=true"))
    assert not exact_app_foreground_evidence(mutate_app("package=" + PACKAGE + " appop=NONE",
                                                "package=com.example.other appop=NONE"))
    footer_start = fixture.index("  mGlobalConfiguration=", app_end)
    bad_last_app = fixture[:app_start] + fixture[app_start:app_end].replace(
        "mHasSurface=true isReadyForDisplay()=true",
        "mHasSurface=false isReadyForDisplay()=false") + fixture[footer_start:]
    bad_last_app = bad_last_app.replace("  mHasPermanentDpad=false",
        "  mHasSurface=true isReadyForDisplay()=true\n  mHasPermanentDpad=false", 1)
    assert not exact_app_foreground_evidence(bad_last_app)
    assert not exact_app_foreground_evidence(fixture.replace("imeInputTarget in display# 0 Window{b0ee4e2",
                                                     "imeInputTarget in display# 0 Window{badc0de"))
    competing = ("  Window #11 Window{badc0de u0 com.example.other/.Activity}:\n"
                 "    mDisplayId=0 package=com.example.other\n"
                 "    isOnScreen=true\n    isVisible=true\n")
    assert not exact_app_foreground_evidence(fixture[:footer_start] + competing + fixture[footer_start:])
    try:
        verify_wm_720("Physical size: 1080x1920\n")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Missing wm override accepted")
    try:
        verify_wm_density_320("Physical density: 420\n")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Missing density override accepted")
    manifest = {
        "projectId": "seven-district-reckoning", "repository": REPOSITORY,
        "branch": BRANCH, "appId": PACKAGE, "versionName": "1.0.0", "versionCode": 11,
        "apk": {"file": APK_NAME, "bytes": APK_BYTES, "sha256": APK_SHA,
                "certificateSha256": CERT_SHA},
        "source": dict(SOURCE_PINS),
        "release": {"tag": RELEASE_TAG, "draft": True, "releaseId": None, "assetId": None},
        "runtime": {"apiLevel": 36, "abi": "x86_64,arm64-v8a",
                    "bridge": "libndk_translation.so", "gpu": GPU_MODE,
                    "image": SYSTEM_IMAGE, "imageRevision": 7,
                    "emulatorVersion": "37.2.12", "buildToolsVersion": "36.1.0"},
    }
    verify_manifest(manifest)
    provenance = {"projectId": "seven-district-reckoning", "repository": REPOSITORY,
                  "branch": BRANCH, "apkFile": APK_NAME,
                  "apkSha256": APK_SHA, "apkBytes": APK_BYTES,
                  "versionCode": 11, "versionName": "1.0.0", "appId": PACKAGE,
                  "certificateSha256": CERT_SHA, "releaseTag": RELEASE_TAG,
                  "releaseDraft": True,
                  "releaseId": 123, "assetId": 456, **SOURCE_PINS}
    verify_provenance(provenance, manifest)
    try:
        verify_provenance({**provenance, "apkSha256": "0" * 64}, manifest)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Wrong fetched APK SHA accepted")
    print("run_probe pure guard self-test: PASS")


class Probe:
    def __init__(self) -> None:
        self.temp, self.workspace, self.sdk, self.apk, self.out, self.avd_home = exact_environment()
        self.user_home = self.temp / "seven-build11-r13-user"
        packet_manifest = Path(__file__).resolve().with_name("manifest.json")
        self.manifest = read_small_json(packet_manifest)
        verify_manifest(self.manifest)
        self.input_dir = self.temp / "seven-build11-r13-input"
        self.provenance_path = self.input_dir / "fetch-provenance.json"
        self.provenance = read_small_json(self.provenance_path)
        verify_provenance(self.provenance, self.manifest)
        fetched_manifest = self.input_dir / "manifest.json"
        if (fetched_manifest.is_symlink() or not fetched_manifest.is_file()
                or digest(fetched_manifest) != digest(packet_manifest)
                or self.provenance.get("manifestSha256") != digest(packet_manifest)):
            raise RuntimeError("Fetched manifest bytes differ from prepared packet/provenance")
        if self.apk.is_symlink() or not self.apk.is_file() or self.apk.stat().st_size != APK_BYTES or digest(self.apk) != APK_SHA:
            raise RuntimeError("Fetched build11 APK bytes/SHA mismatch")
        if (self.workspace / "output").is_symlink() or self.out.is_symlink():
            raise RuntimeError("Evidence output may not be a symlink")
        if not self.out.is_dir():
            raise RuntimeError("Bootstrap-owned evidence output is absent")
        owned_run = read_small_json(self.out / "owned-run.json")
        if (owned_run.get("owner") != "seven-build11-r13-kvm"
                or owned_run.get("runId") != os.environ["GITHUB_RUN_ID"]
                or owned_run.get("headSha") != os.environ.get("GITHUB_SHA")):
            raise RuntimeError("Evidence output lacks this run's bootstrap ownership marker")
        self.frames = self.out / "native-frames"
        if self.frames.exists() or self.frames.is_symlink():
            raise RuntimeError("Native frame output already exists or is linked")
        self.frames.mkdir(parents=True, exist_ok=False)
        self.adb = str(self.sdk / "platform-tools" / "adb")
        self.emulator = str(self.sdk / "emulator" / "emulator")
        self.avdmanager = str(self.sdk / "cmdline-tools" / "latest" / "bin" / "avdmanager")
        self.apksigner = str(self.sdk / "build-tools" / "36.1.0" / "apksigner")
        self.aapt2 = str(self.sdk / "build-tools" / "36.1.0" / "aapt2")
        self.run_id = os.environ["GITHUB_RUN_ID"]
        self.avd_name = "SevenBuild11_" + self.run_id
        self.deadline = time.monotonic() + FLOW_SECONDS
        self.proc: subprocess.Popen | None = None
        self.recorder: subprocess.Popen | None = None
        self.bootlog_file = None
        self.app_pid: int | None = None
        self.start_tap_epoch: float | None = None
        self.core_hud_epoch: float | None = None
        self.world_until: float | None = None
        self.booted = False
        self.sequence = 0
        self.ui_dump_attempts = 0
        self.notice_dismissals = 0
        self.remote_movie = "/sdcard/SevenBuild11_" + self.run_id + ".mp4"
        self.report: dict = {
            "schemaVersion": 1, "projectId": "seven-district-reckoning",
            "status": "PREPARING", "runId": self.run_id,
            "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "repository": REPOSITORY, "branch": BRANCH,
            "host": "github-actions-ubuntu-24.04-kvm", "deviceKind": "OFFICIAL_ANDROID_EMULATOR_KVM",
            "physicalDevice": False, "apkSha256": APK_SHA, "apkBytes": APK_BYTES,
            "certificateSha256Expected": CERT_SHA, "versionCode": 11,
            "systemImage": SYSTEM_IMAGE, "gpuRequested": GPU_MODE,
            "accelerationRequested": "on", "flowDeadlineSeconds": FLOW_SECONDS,
            "titleWaitMaximumSeconds": TITLE_SECONDS, "hudWaitMaximumSeconds": HUD_SECONDS,
            "worldWaitMaximumSeconds": WORLD_SECONDS,
            "ocrChildMaximumSeconds": OCR_SECONDS, "ocrChildOmpThreadLimit": 1,
            "nativeImagesResampled": False, "screenSizeOverride": [720, 1280],
            "screenDensityOverrideDpi": 320, "densityOverrideTestOnly": True,
            "expectedOriginalLandscapePNG": [1280, 720],
            "bootVerified": False, "installedIdentityVerified": False,
            "startMenuObserved": False, "startTapCount": 0,
            "worldReadyEventObserved": False, "gameplayHudObserved": False,
            "coreGameplayObserved": False,
            "joystickVisibleProof": False, "movementGestureExecuted": False,
            "nativeRuntimeReady": False, "nativeGameplayAccepted": False,
            "firstChapterCompletedVerified": False, "physicalDeviceRequirementSatisfied": False,
            "gameStateInjected": False, "gameSourceChangedByProbe": False,
            "storeWrites": 0, "networkCallsByDriver": 0,
            "captures": [], "inputs": [], "limits": [
                "Emulator readiness is not physical-device or human-tester evidence",
                "One visible start tap and optional observed joystick swipe do not verify mission completion",
                "Runtime findings require separate root visual gameplay acceptance",
            ],
        }
        self.write_json("manifest-used.json", self.manifest)
        self.write_json("fetch-provenance.json", self.provenance)
        self.save()

    def write_json(self, name: str, value: object) -> None:
        (self.out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def save(self) -> None:
        path = self.out / "native-observation.json"
        temporary = self.out / "native-observation.json.tmp"
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def command(self, argv: list[str], timeout: float = 20, *, allow_failure: bool = False,
                input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Absolute native flow deadline exceeded")
        result = subprocess.run(argv, input=input_bytes, capture_output=True,
                                timeout=min(timeout, remaining), check=False)
        if result.returncode != 0 and not allow_failure:
            raise RuntimeError("Pinned native command failed: " + Path(argv[0]).name + " " + " ".join(argv[1:4]))
        return result

    def device(self, *args: str, timeout: float = 20, allow_failure: bool = False) -> subprocess.CompletedProcess:
        return self.command([self.adb, "-s", SERIAL, *args], timeout, allow_failure=allow_failure)

    def capture(self, label: str) -> tuple[object, str, str]:
        """Keep adb's original PNG; OCR never changes tap coordinates or source bytes."""
        from PIL import Image

        self.sequence += 1
        name = f"{self.sequence:03d}-{label}.png"
        path = self.frames / name
        requested = utc_now()
        raw = self.device("exec-out", "screencap", "-p", timeout=25).stdout
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("Native screencap did not return original PNG bytes")
        path.write_bytes(raw)
        with Image.open(io.BytesIO(raw)) as source:
            width, height = source.size
            image = source.convert("RGB")
        receipt = {"file": name, "sha256": hashlib.sha256(raw).hexdigest(),
                   "bytes": len(raw), "nativeSize": [width, height],
                   "captureRequestedAtUtc": requested, "originalWrittenAtUtc": utc_now(),
                   "originalPNG": True, "resampled": False, "ocrComplete": False}
        self.report["captures"].append(receipt)
        self.save()
        if (width, height) != (1280, 720):
            raise RuntimeError("Original game PNG is not pinned 1280x720 landscape")
        if "ownedRotationReadback" in self.report:
            self.report["ownedRotationReadback"]["actualLandscapeVerifiedByOriginalPNG"] = True
        argv = ["tesseract", str(path), "stdout", "-l", "chi_tra+eng", "--psm", "11", "tsv"]
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Absolute flow deadline exceeded before OCR")
        child_env = os.environ.copy()
        child_env["OMP_THREAD_LIMIT"] = "1"
        child_env["OMP_NUM_THREADS"] = "1"
        began = time.monotonic()
        budget = min(OCR_SECONDS, remaining)
        try:
            ocr = subprocess.run(argv, capture_output=True, timeout=budget, env=child_env)
            stdout, stderr, code, timed_out = ocr.stdout, ocr.stderr, ocr.returncode, False
        except subprocess.TimeoutExpired as error:
            stdout, stderr, code, timed_out = error.stdout or b"", error.stderr or b"", None, True
        path.with_suffix(".tsv").write_bytes(stdout)
        path.with_suffix(".ocr.stderr.txt").write_bytes(stderr)
        ocr_receipt = {"frame": name, "maximumSeconds": OCR_SECONDS,
                       "effectiveBudgetSeconds": round(budget, 3),
                       "elapsedSeconds": round(time.monotonic() - began, 3),
                       "exitCode": code, "timedOut": timed_out,
                       "childOmpThreadLimit": 1, "globalEnvironmentMutated": False}
        path.with_suffix(".ocr-receipt.json").write_text(json.dumps(ocr_receipt, indent=2) + "\n")
        receipt["ocrReceipt"] = ocr_receipt
        self.save()
        if timed_out or code != 0:
            raise RuntimeError("Bounded OCR failed; original PNG and child stderr retained")
        tsv = stdout.decode("utf-8", "replace")
        words = [row.get("text", "") for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)]
        receipt["ocrComplete"] = True
        receipt["ocrText"] = " ".join(word for word in words if word)[:4096]
        self.save()
        return image, tsv, name

    def dismiss_systemui_notice(self, image: object, tsv: str, frame: str) -> bool:
        title = label_box(tsv, "Viewing full screen")
        instruction = label_box(tsv, "To exit, swipe down from the top of your screen")
        if not title or not instruction:
            return False
        if self.notice_dismissals >= MAX_SYSTEMUI_DISMISSALS:
            raise RuntimeError("SystemUI education still visible after two same-frame-proven taps")
        xml = None
        while self.ui_dump_attempts < MAX_UI_DUMPS:
            self.ui_dump_attempts += 1
            attempt = self.ui_dump_attempts
            remote = "/sdcard/SevenBuild11_" + self.run_id + "_notice_" + str(attempt) + ".xml"
            prefix = self.frames / (Path(frame).stem + f".uiautomator-{attempt}")
            try:
                dumped = self.device("shell", "uiautomator", "dump", remote,
                                     timeout=30, allow_failure=True)
                dump_code, dump_out, dump_err = dumped.returncode, dumped.stdout, dumped.stderr
            except subprocess.TimeoutExpired as error:
                dump_code, dump_out, dump_err = -1, error.stdout or b"", error.stderr or b""
            (Path(str(prefix) + ".dump.stdout.txt")).write_bytes(dump_out)
            (Path(str(prefix) + ".dump.stderr.txt")).write_bytes(dump_err)
            try:
                cat = self.device("exec-out", "cat", remote, timeout=20, allow_failure=True)
                cat_code, cat_out, cat_err = cat.returncode, cat.stdout, cat.stderr
            except subprocess.TimeoutExpired as error:
                cat_code, cat_out, cat_err = -1, error.stdout or b"", error.stderr or b""
            (Path(str(prefix) + ".cat.stdout.txt")).write_bytes(cat_out)
            (Path(str(prefix) + ".cat.stderr.txt")).write_bytes(cat_err)
            xml = valid_uiautomator_xml(cat_out, cat_code) if dump_code == 0 else None
            attempt_record = {"attempt": attempt, "maximumAttempts": MAX_UI_DUMPS,
                              "basisNativeFrame": frame, "remoteXML": remote,
                              "dumpExitCode": dump_code, "catExitCode": cat_code,
                              "validActualXML": xml is not None, "tapPerformed": False}
            self.report.setdefault("systemUiDumpAttempts", []).append(attempt_record)
            self.write_json(Path(str(prefix) + ".receipt.json").name, attempt_record)
            self.save()
            if xml is not None:
                (Path(str(prefix) + ".xml")).write_text(xml, encoding="utf-8")
                break
            if attempt < MAX_UI_DUMPS and self.deadline - time.monotonic() > 3:
                time.sleep(2)
                image, tsv, frame = self.capture("systemui-xml-retry")
                if not (label_box(tsv, "Viewing full screen") and label_box(tsv, "To exit, swipe down from the top of your screen")):
                    return False
        if xml is None:
            self.report["infrastructureHoldReason"] = "SYSTEMUI_XML_UNAVAILABLE_AFTER_TWO_OFFICIAL_DUMPS"
            self.save()
            raise RuntimeError("Visible SystemUI notice lacks verified XML; no tap")
        proof = systemui_notice_from_frame(xml, tsv, image.width, image.height)
        if proof is None:
            raise RuntimeError("SystemUI Got it ownership and same-panel OCR were not proven; no tap")
        box = proof["buttonBounds"]
        point = [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2]
        action = {"action": "dismiss_systemui_immersive_education", "caption": "Got it",
                  "basisNativeFrame": frame, "samePanelEvidence": proof,
                  "nativePoint": point, "permissionGrant": False, "commandSucceeded": False}
        self.report["inputs"].append(action)
        self.save()
        self.device("shell", "input", "tap", str(point[0]), str(point[1]))
        self.notice_dismissals += 1
        action["commandSucceeded"] = True
        attempt_record["tapPerformed"] = True
        self.report["systemUiNoticeDismissals"] = self.notice_dismissals
        self.write_json(Path(str(prefix) + ".receipt.json").name, attempt_record)
        self.save()
        # Record the outcome before another input. On persistence, the next
        # loop captures a fresh native frame and repeats XML ownership proof.
        time.sleep(2)
        observed_image, observed_tsv, observed_frame = self.capture("systemui-posttap-observation")
        still_visible = bool(label_box(observed_tsv, "Viewing full screen")
                             and label_box(observed_tsv, "To exit, swipe down from the top of your screen"))
        self.report.setdefault("systemUiPostTapObservations", []).append({
            "afterDismissal": self.notice_dismissals,
            "basisNativeFrame": observed_frame,
            "educationStillVisible": still_visible,
        })
        self.save()
        if still_visible and self.notice_dismissals < MAX_SYSTEMUI_DISMISSALS:
            time.sleep(2)
        return True

    def wait_visible_start(self) -> tuple[object, str, str, list[int]]:
        until = min(self.deadline, time.monotonic() + TITLE_SECONDS)
        while time.monotonic() < until:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError("Owned emulator exited before start-menu proof")
            image, tsv, frame = self.capture("cold-title-wait")
            if self.dismiss_systemui_notice(image, tsv, frame):
                continue
            box = label_box(tsv, "開始新遊戲")
            if box:
                if not (0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height):
                    raise RuntimeError("Observed start caption outside original native frame")
                self.report["startMenuObserved"] = True
                self.report["startMenuProof"] = {"basisNativeFrame": frame, "ocrBounds": box}
                self.save()
                return image, tsv, frame, box
            time.sleep(min(10, max(0, until - time.monotonic())))
        raise RuntimeError("Unique visible 開始新遊戲 OCR not observed within bounded title wait")

    def tap_visible_start_once(self, frame: str, box: list[int]) -> None:
        if self.report["startTapCount"] != 0:
            raise RuntimeError("Start tap already attempted")
        self.verify_foreground("before-visible-start-tap")
        point = [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2]
        action = {"action": "tap_start_new_game", "caption": "開始新遊戲",
                  "basisNativeFrame": frame, "ocrBounds": box,
                  "nativePoint": point, "commandSucceeded": False,
                  "tapRequestedAtUtc": utc_now(), "tapRequestedAtEpochSeconds": time.time(),
                  "tapRequestedAtMonotonicSeconds": time.monotonic()}
        self.start_tap_epoch = action["tapRequestedAtEpochSeconds"]
        self.world_until = min(self.deadline, time.monotonic() + WORLD_SECONDS)
        self.report["startTapCount"] = 1
        self.report["inputs"].append(action)
        self.save()
        self.device("shell", "input", "tap", str(point[0]), str(point[1]))
        action["commandSucceeded"] = True
        action["tapCommandCompletedAtUtc"] = utc_now()
        action["tapCommandCompletedAtMonotonicSeconds"] = time.monotonic()
        self.save()

    def app_logcat(self, name: str) -> str:
        if self.app_pid is None:
            raise RuntimeError("No owned app PID for logcat")
        result = self.device("logcat", "-d", "-v", "epoch", "--pid=" + str(self.app_pid), timeout=30)
        raw = result.stdout
        retained, truncated = retained_logcat(raw)
        (self.out / name).write_bytes(retained)
        self.report["appLogcatFullBytes"] = len(raw)
        self.report["appLogcatFullSha256"] = hashlib.sha256(raw).hexdigest()
        self.report["appLogcatRetainedBytes"] = len(retained)
        self.report["appLogcatRetainedSha256"] = hashlib.sha256(retained).hexdigest()
        self.report["appLogcatTruncatedToTail"] = truncated
        return retained.decode("utf-8", "replace")

    def verify_foreground(self, label: str) -> None:
        window = self.device("shell", "dumpsys", "window", "windows", timeout=25)
        (self.out / ("foreground-" + label + ".txt")).write_bytes(window.stdout)
        dump = window.stdout.decode("utf-8", "replace")
        if not exact_app_foreground_evidence(dump):
            raise RuntimeError("Exact app lacks sufficient foreground evidence: " + label)
        basis = ("currentFocus" if re.search(r"^[ \t]*mCurrentFocus\b", dump, re.M)
                 else "api36VisibleWindowAndImeTargets")
        self.report.setdefault("foregroundProofs", []).append({
            "phase": label, "source": "foreground-" + label + ".txt",
            "package": PACKAGE, "basis": basis})
        self.save()

    @staticmethod
    def hud_visible(tsv: str) -> bool:
        return all(label_box(tsv, text) for text in ("MAIN", "攻擊", "暫停"))

    def wait_gameplay_hud(self) -> tuple[object, str, str] | None:
        """Observe playable core before waiting for the outer world stream."""
        until = min(self.world_until or self.deadline, time.monotonic() + HUD_SECONDS)
        while time.monotonic() < until:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError("Owned emulator exited before core gameplay HUD")
            image, tsv, frame = self.capture("core-gameplay-hud-wait")
            if self.hud_visible(tsv):
                self.verify_foreground("core-gameplay-hud")
                self.core_hud_epoch = time.time()
                self.report["gameplayHudObserved"] = True
                self.report["coreGameplayObserved"] = True
                self.report["gameplayHudProof"] = {"basisNativeFrame": frame,
                                                    "ocrLabels": ["MAIN", "攻擊", "暫停"],
                                                    "observedAtUtc": utc_now(),
                                                    "observedAtEpochSeconds": self.core_hud_epoch,
                                                    "observedAtMonotonicSeconds": time.monotonic(),
                                                    "worldReadyNotRequiredForCorePlay": True}
                self.save()
                return image, tsv, frame
            time.sleep(min(10, max(0, until - time.monotonic())))
        self.report["earlyCoreHudWaitTimedOut"] = True
        self.report["joystickSwipeSkippedReason"] = "NO_VISIBLE_HUD_DURING_EARLY_CORE_WAIT"
        self.save()
        return None

    def observe_world(self) -> tuple[object, str, str]:
        until = self.world_until or self.deadline
        began = time.monotonic()
        observed_hud = None
        polls = 0
        while time.monotonic() < until:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError("Owned emulator exited during world-ready observation")
            pid_text = self.device("shell", "pidof", PACKAGE, allow_failure=True).stdout.decode().strip()
            if pid_text != str(self.app_pid):
                raise RuntimeError("Owned app PID changed during native observation")
            image, tsv, frame = self.capture("world-observation")
            if self.hud_visible(tsv):
                observed_hud = (image, tsv, frame)
                if not self.report["gameplayHudObserved"]:
                    self.verify_foreground("late-gameplay-hud")
                    self.core_hud_epoch = time.time()
                    self.report["gameplayHudObserved"] = True
                    self.report["coreGameplayObserved"] = True
                    self.report["gameplayHudProof"] = {"basisNativeFrame": frame,
                                                        "ocrLabels": ["MAIN", "攻擊", "暫停"],
                                                        "observedAtUtc": utc_now(),
                                                        "observedAtEpochSeconds": self.core_hud_epoch,
                                                        "observedAfterEarlyHudWait": True}
                    self.save()
            polls += 1
            log = self.app_logcat("owned-app-logcat-current.txt")
            if self.start_tap_epoch is not None:
                self.report["postStartEmulatorFpsDiagnostic"] = post_start_emulator_fps(log, self.start_tap_epoch)
                self.report["postStartEmulatorFpsDiagnostic"]["sourceFile"] = "owned-app-logcat-current.txt"
                self.report["postStartEmulatorFpsDiagnostic"]["sourceSha256"] = self.report["appLogcatRetainedSha256"]
            if self.core_hud_epoch is not None:
                self.report["postHudEmulatorFpsDiagnostic"] = post_start_emulator_fps(log, self.core_hud_epoch)
                self.report["postHudEmulatorFpsDiagnostic"]["sourceFile"] = "owned-app-logcat-current.txt"
                self.report["postHudEmulatorFpsDiagnostic"]["sourceSha256"] = self.report["appLogcatRetainedSha256"]
            events = world_ready_events(log)
            if events:
                sample = events[-1]
                self.report["worldReadyEventObserved"] = True
                self.report["worldReadyEvent"] = sample
                proof_name = "world-ready-logcat-proof.txt"
                proof_bytes = (self.out / "owned-app-logcat-current.txt").read_bytes()
                (self.out / proof_name).write_bytes(proof_bytes)
                self.report["worldReadyProof"] = {"appPid": self.app_pid,
                                                   "source": proof_name,
                                                   "sourceSha256": hashlib.sha256(proof_bytes).hexdigest(),
                                                   "exactEventCount": len(events)}
                self.save()
            self.report["worldObservationPolls"] = polls
            self.report["worldObservationElapsedSeconds"] = round(time.monotonic() - began, 3)
            self.report["worldObservationSinceStartTapSeconds"] = round(time.time() - (self.start_tap_epoch or time.time()), 3)
            self.save()
            if self.report["worldReadyEventObserved"] and observed_hud is not None:
                # Preserve a frame captured after both evidence conditions became true.
                ready_image, ready_tsv, ready_frame = self.capture("world-ready-gameplay-hud")
                if not self.hud_visible(ready_tsv):
                    raise RuntimeError("Gameplay HUD disappeared on world-ready final native frame")
                self.report["worldReadyGameplayFrame"] = ready_frame
                self.save()
                return ready_image, ready_tsv, ready_frame
            time.sleep(min(20, max(0, until - time.monotonic())))
        raise RuntimeError("Exact world_ready event and gameplay HUD not both observed within bounded wait")

    def maybe_swipe_observed_joystick(self, image: object, frame: str) -> None:
        """One swipe only if a unique circle is visible where build11 source lays it out."""
        import cv2
        import numpy as np
        from PIL import ImageChops

        gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
        y0, y1, x1 = 400, image.height, 275
        roi = gray[y0:y1, 0:x1]
        circles = cv2.HoughCircles(roi, cv2.HOUGH_GRADIENT, dp=1.2, minDist=22,
                                  param1=80, param2=24, minRadius=35, maxRadius=150)
        candidates = [] if circles is None else [
            [float(x), float(y + y0), float(radius)] for x, y, radius in circles[0]
        ]
        # Build11 source: center=(safe_margin+radius, viewport_height-safe_margin-radius-24).
        # Phone defaults are safe_margin=12, radius=56 logical units. Infer the
        # native scale from each observed ring radius; never assume density=1.
        candidates = [row for row in candidates if 35 <= row[2] <= 150
                      and abs(row[0] - row[2] * 68 / 56) <= max(20, row[2] * .35)
                      and abs(row[1] - (image.height - row[2] * 92 / 56)) <= max(25, row[2] * .35)]
        self.report["joystickImageInspection"] = {
            "basisNativeFrame": frame, "originalFrameSize": [image.width, image.height],
            "searchROI": [0, y0, x1, y1], "observedCircleCandidates": candidates,
            "build11TouchLayoutSourceSha256": TOUCH_LAYOUT_SOURCE_SHA,
            "build11DeviceProfilesJsonSha256": DEVICE_PROFILES_SOURCE_SHA,
            "sourceLayout": "phone FloatingJoystick radius 56 and safe margin 12, scaled to native pixels; screenshot must show a unique ring",
            "sourceLayoutAloneNeverAuthorizesInput": True,
        }
        if len(candidates) != 1:
            self.report["joystickSwipeSkippedReason"] = "NO_UNIQUE_VISIBLE_JOYSTICK_RING"
            self.save()
            return
        x, y, radius = candidates[0]
        start = [round(x), round(y)]
        end = [round(x + radius * .72), round(y)]
        if not (0 <= start[0] < image.width and 0 <= end[0] < image.width
                and 0 <= start[1] < image.height and 0 <= end[1] < image.height):
            self.report["joystickSwipeSkippedReason"] = "OBSERVED_GESTURE_LEAVES_NATIVE_FRAME"
            self.save()
            return
        self.report["joystickVisibleProof"] = True
        self.verify_foreground("before-observed-joystick-swipe")
        action = {"action": "joystick_swipe", "basisNativeFrame": frame,
                  "observedCircle": candidates[0], "nativeGesture": [*start, *end, 1800],
                  "commandSucceeded": False}
        self.report["inputs"].append(action)
        self.save()
        self.device("shell", "input", "swipe", *map(str, action["nativeGesture"]))
        action["commandSucceeded"] = True
        self.report["movementGestureExecuted"] = True
        self.save()
        after, _, after_frame = self.capture("after-observed-joystick-swipe")
        crop = (int(image.width * .18), int(image.height * .34),
                int(image.width * .82), int(image.height * .70))
        delta = np.asarray(ImageChops.difference(image.crop(crop), after.crop(crop)))
        self.report["movementFrameDifference"] = {
            "before": frame, "after": after_frame, "comparisonCrop": list(crop),
            "fractionPixelsChannelDeltaAbove20": float((delta.max(axis=2) > 20).mean()),
            "pixelChangeAloneIsNotPlayerPhysicsAcceptance": True,
        }
        self.save()

    def verify_sdk_and_apk(self) -> None:
        expected_files = (self.adb, self.emulator, self.avdmanager, self.apksigner, self.aapt2)
        if any(not Path(path).is_file() or Path(path).is_symlink() for path in expected_files):
            raise RuntimeError("Pinned official SDK tool is absent or linked")
        versions = {
            "emulator": (self.sdk / "emulator" / "source.properties", "37.2.12"),
            "buildTools": (self.sdk / "build-tools" / "36.1.0" / "source.properties", "36.1.0"),
            "systemImage": (self.sdk / "system-images" / "android-36" / "google_apis" / "x86_64" / "source.properties", "7"),
        }
        actual = {}
        for key, (path, revision) in versions.items():
            value = read_properties(path).get("Pkg.Revision")
            if value != revision:
                raise RuntimeError("Pinned official SDK revision mismatch: " + key)
            actual[key] = value
        emulator_version = self.command([self.emulator, "-version"], timeout=15)
        version_text = (emulator_version.stdout + emulator_version.stderr).decode("utf-8", "replace")
        if not re.search(r"Android emulator version 37\.2\.12(?:\b|\.)", version_text):
            raise RuntimeError("Actual official emulator binary version mismatch")
        self.report["sdkRevisionsVerified"] = actual
        self.report["emulatorVersionOutput"] = version_text[:2000]
        signature = self.command([self.apksigner, "verify", "--print-certs", str(self.apk)], timeout=45)
        signature_text = (signature.stdout + signature.stderr).decode("utf-8", "replace")
        certs = re.findall(r"certificate SHA-256 digest:\s*([0-9a-f]{64})", signature_text, re.I)
        if [cert.lower() for cert in certs] != [CERT_SHA]:
            raise RuntimeError("Exact APK signing certificate differs from build11 pin")
        self.report["certificateSha256Verified"] = CERT_SHA
        badging = self.command([self.aapt2, "dump", "badging", str(self.apk)], timeout=45)
        package_line = next((line for line in badging.stdout.decode("utf-8", "replace").splitlines()
                             if line.startswith("package: ")), "")
        identity = re.search(r"name='([^']+)'\s+versionCode='([^']+)'\s+versionName='([^']+)'", package_line)
        if not identity or identity.groups() != (PACKAGE, "11", "1.0.0"):
            raise RuntimeError("Actual APK package/version differs from build11 pin")
        self.report["apkManifestIdentityVerified"] = {
            "appId": identity.group(1), "versionCode": 11, "versionName": identity.group(3)}
        acceleration = self.command([self.emulator, "-accel-check"], timeout=20)
        accel_text = (acceleration.stdout + acceleration.stderr).decode("utf-8", "replace")
        if "KVM" not in accel_text or "usable" not in accel_text.lower():
            raise RuntimeError("Official KVM acceleration is not usable; no TCG fallback")
        self.report["officialAccelCheck"] = accel_text[:2000]
        gpu_help = self.command([self.emulator, "-help-gpu"], timeout=20, allow_failure=True)
        (self.out / "emulator-help-gpu.stdout.txt").write_bytes(gpu_help.stdout)
        (self.out / "emulator-help-gpu.stderr.txt").write_bytes(gpu_help.stderr)
        if gpu_help.returncode != 0 or not re.search(r"(?<![\w])swangle(?![\w])",
                                                   (gpu_help.stdout + gpu_help.stderr).decode("utf-8", "replace")):
            raise RuntimeError("Pinned official emulator does not advertise swangle; no GPU fallback")
        self.report["officialGpuHelpAdvertisesSwangle"] = True
        self.save()

    def create_owned_avd(self) -> None:
        attached = self.command([self.adb, "devices"], timeout=20).stdout.decode("utf-8", "replace")
        rows = attached.strip().splitlines()[1:]
        if any(row.strip() for row in rows):
            raise RuntimeError("Unexpected preexisting adb device; no device reuse")
        for port in (AVD_PORT, AVD_PORT + 1):
            with socket.socket() as reserved:
                reserved.bind(("127.0.0.1", port))
        if self.avd_home.is_symlink() or self.user_home.is_symlink():
            raise RuntimeError("Owned AVD/user home may not be linked")
        self.avd_home.mkdir(parents=True, exist_ok=True)
        self.user_home.mkdir(parents=True, exist_ok=True)
        data = self.avd_home / (self.avd_name + ".avd")
        registry = self.avd_home / (self.avd_name + ".ini")
        if data.exists() or registry.exists():
            raise RuntimeError("Owned AVD already exists; no overwrite or retry")
        try:
            created = self.command([self.avdmanager, "create", "avd", "-n", self.avd_name,
                                    "-k", SYSTEM_IMAGE, "--device", "pixel_2",
                                    "--path", str(data)], timeout=90, allow_failure=True,
                                   input_bytes=b"no\n")
        except subprocess.TimeoutExpired as error:
            (self.out / "avd-create.stdout.txt").write_bytes(error.stdout or b"")
            (self.out / "avd-create.stderr.txt").write_bytes(error.stderr or b"")
            raise RuntimeError("Official AVD creation exceeded one bounded attempt") from None
        (self.out / "avd-create.stdout.txt").write_bytes(created.stdout)
        (self.out / "avd-create.stderr.txt").write_bytes(created.stderr)
        self.report["officialAvdCreateExitCode"] = created.returncode
        self.save()
        if created.returncode != 0:
            raise RuntimeError("Official isolated avdmanager create failed; no retry")
        if registry.is_file():
            (self.out / "owned-avd-registry.ini.txt").write_bytes(registry.read_bytes())
        if (data / "config.ini").is_file():
            (self.out / "owned-avd-config.ini.txt").write_bytes((data / "config.ini").read_bytes())
        listing = self.command([self.emulator, "-list-avds"], timeout=20)
        (self.out / "emulator-list-avds.txt").write_bytes(listing.stdout)
        self.report["ownedAvdRegistry"] = verify_avd_registry(
            registry, data, self.avd_name, listing.stdout.decode("utf-8", "replace"), self.temp)
        self.save()

    def boot_owned_emulator(self) -> None:
        self.bootlog_file = (self.out / "owned-emulator.log").open("wb")
        argv = [self.emulator, "-avd", self.avd_name, "-no-window", "-no-boot-anim",
                "-no-snapshot", "-no-audio", "-accel", "on", "-gpu", GPU_MODE,
                "-memory", "2048", "-cores", "2", "-camera-back", "none",
                "-camera-front", "none", "-port", str(AVD_PORT)]
        self.proc = subprocess.Popen(argv, stdout=self.bootlog_file,
                                     stderr=subprocess.STDOUT, start_new_session=True)
        self.report["ownedEmulatorPid"] = self.proc.pid
        self.report["ownedAvdName"] = self.avd_name
        self.save()
        until = min(self.deadline, time.monotonic() + 240)
        while time.monotonic() < until:
            if self.proc.poll() is not None:
                raise RuntimeError("Owned KVM emulator exited before boot completed")
            boot = self.device("shell", "getprop", "sys.boot_completed", timeout=15,
                               allow_failure=True)
            if boot.returncode == 0 and boot.stdout.strip() == b"1":
                break
            time.sleep(min(3, max(0, until - time.monotonic())))
        else:
            raise RuntimeError("Owned KVM emulator boot exceeded deadline")
        self.booted = True  # Collect logcat even if later ABI or renderer verification fails.
        abi = self.device("shell", "getprop", "ro.product.cpu.abilist64").stdout.decode().strip()
        bridge = self.device("shell", "getprop", "ro.dalvik.vm.native.bridge").stdout.decode().strip()
        if "arm64-v8a" not in abi.split(",") or bridge != "libndk_translation.so":
            raise RuntimeError("Actual guest ARM64 native bridge absent; no APK install")
        bootlog = (self.out / "owned-emulator.log").read_text(encoding="utf-8", errors="replace")
        if not re.search(r"gles_mode_selected:swangle\b", bootlog):
            raise RuntimeError("Actual owned GLES selection is not swangle; no renderer fallback")
        self.report.update(bootVerified=True, actualGuestAbi64=abi,
                           actualGuestNativeBridge=bridge, actualSwangleGlesSelectionVerified=True)
        self.report["actualGraphicsModeLines"] = [line for line in bootlog.splitlines()
            if any(token in line for token in ("emuglConfig_init", "Graphics Adapter", "Graphics API Version"))][:30]
        self.save()

    def set_owned_720p_size(self) -> None:
        before = self.device("shell", "wm", "size")
        (self.out / "owned-wm-size-before.txt").write_bytes(before.stdout)
        if "Override size:" in before.stdout.decode("utf-8", "replace"):
            raise RuntimeError("Fresh owned guest already has a size override")
        changed = self.device("shell", "wm", "size", "720x1280", allow_failure=True)
        (self.out / "owned-wm-size-set.stdout.txt").write_bytes(changed.stdout)
        (self.out / "owned-wm-size-set.stderr.txt").write_bytes(changed.stderr)
        if changed.returncode != 0:
            raise RuntimeError("One owned 720x1280 wm size command failed; no fallback")
        after = self.device("shell", "wm", "size")
        (self.out / "owned-wm-size-after.txt").write_bytes(after.stdout)
        self.report["ownedScreenSizeReadback"] = verify_wm_720(after.stdout.decode("utf-8", "replace"))
        self.report["ownedScreenSizeReadback"].update(
            mutationAttempts=1, appliedBeforeInstallAndLaunch=True,
            testOnly=True, priorRunModified=False)
        density_before = self.device("shell", "wm", "density")
        (self.out / "owned-wm-density-before.txt").write_bytes(density_before.stdout)
        if "Override density:" in density_before.stdout.decode("utf-8", "replace"):
            raise RuntimeError("Fresh owned guest already has a density override")
        density_set = self.device("shell", "wm", "density", "320", allow_failure=True)
        (self.out / "owned-wm-density-set.stdout.txt").write_bytes(density_set.stdout)
        (self.out / "owned-wm-density-set.stderr.txt").write_bytes(density_set.stderr)
        if density_set.returncode != 0:
            raise RuntimeError("One owned 320 dpi override failed; no fallback")
        density_after = self.device("shell", "wm", "density")
        (self.out / "owned-wm-density-after.txt").write_bytes(density_after.stdout)
        self.report["ownedScreenDensityReadback"] = verify_wm_density_320(density_after.stdout.decode("utf-8", "replace"))
        self.report["ownedScreenDensityReadback"].update(
            mutationAttempts=1, appliedBeforeInstallAndLaunch=True, testOnly=True)
        rotation_before = {
            "accelerometerRotation": self.device("shell", "settings", "get", "system", "accelerometer_rotation").stdout.decode().strip(),
            "userRotation": self.device("shell", "settings", "get", "system", "user_rotation").stdout.decode().strip(),
        }
        self.report["ownedRotationBefore"] = rotation_before
        self.device("shell", "settings", "put", "system", "accelerometer_rotation", "0")
        self.device("shell", "settings", "put", "system", "user_rotation", "1")
        rotation_after = {
            "accelerometerRotation": self.device("shell", "settings", "get", "system", "accelerometer_rotation").stdout.decode().strip(),
            "userRotation": self.device("shell", "settings", "get", "system", "user_rotation").stdout.decode().strip(),
        }
        (self.out / "owned-rotation-readback.json").write_text(json.dumps(rotation_after, indent=2) + "\n")
        if rotation_after != {"accelerometerRotation": "0", "userRotation": "1"}:
            raise RuntimeError("Owned landscape rotation readback mismatch")
        self.report["ownedRotationReadback"] = {**rotation_after, "testOnly": True,
                                                  "actualLandscapeVerifiedByOriginalPNG": False}
        self.save()

    def install_and_launch(self) -> None:
        self.device("install", str(self.apk), timeout=120)
        installed = self.device("shell", "dumpsys", "package", PACKAGE, timeout=25).stdout.decode("utf-8", "replace")
        if not re.search(r"\bversionCode=11\b", installed) or "versionName=1.0.0" not in installed:
            raise RuntimeError("Installed owned package/version differs from pinned APK")
        resolved_lines = self.device("shell", "cmd", "package", "resolve-activity", "--brief", PACKAGE).stdout.decode("utf-8", "replace").strip().splitlines()
        if not resolved_lines or resolved_lines[-1].strip() != ALIAS:
            raise RuntimeError("Actual MAIN launcher alias differs; no nonexported activity attempted")
        self.report["installedIdentityVerified"] = True
        self.report["resolvedLaunchActivity"] = ALIAS
        self.device("logcat", "-c")
        start = self.device("shell", "am", "start", "-W", "-n", ALIAS, timeout=50)
        (self.out / "owned-am-start.txt").write_bytes(start.stdout + b"\n" + start.stderr)
        until = min(self.deadline, time.monotonic() + 40)
        while time.monotonic() < until:
            pid_text = self.device("shell", "pidof", PACKAGE, allow_failure=True).stdout.decode().strip()
            if re.fullmatch(r"[1-9][0-9]*", pid_text):
                self.app_pid = int(pid_text)
                break
            time.sleep(2)
        if self.app_pid is None:
            raise RuntimeError("Pinned app did not acquire one native process PID")
        self.report["ownedAppPidAtLaunch"] = self.app_pid
        self.save()

    def start_owned_video(self) -> None:
        self.recorder = subprocess.Popen(
            [self.adb, "-s", SERIAL, "shell", "screenrecord", "--time-limit", "90", self.remote_movie],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        if self.recorder.poll() is not None:
            raise RuntimeError("Owned screenrecord ended before visible start tap")
        self.report["nativeVideoCaptureStarted"] = True
        self.report["nativeVideoRemotePath"] = self.remote_movie
        self.save()

    def collect_final_logcat(self) -> None:
        if not self.booted:
            self.report["guestLogcatUnavailableReason"] = "NO_VERIFIED_BOOTED_GUEST"
            return
        if self.app_pid is not None:
            try:
                app = subprocess.run([self.adb, "-s", SERIAL, "logcat", "-d", "-v", "epoch",
                                      "--pid=" + str(self.app_pid)], capture_output=True, timeout=30)
                retained, truncated = retained_logcat(app.stdout)
                (self.out / "owned-app-logcat-final.txt").write_bytes(retained)
                self.report["finalAppLogcatFullBytes"] = len(app.stdout)
                self.report["finalAppLogcatFullSha256"] = hashlib.sha256(app.stdout).hexdigest()
                self.report["finalAppLogcatRetainedSha256"] = hashlib.sha256(retained).hexdigest()
                self.report["finalAppLogcatTruncatedToTail"] = truncated
            except subprocess.TimeoutExpired:
                self.report["finalAppLogcatUnavailableReason"] = "APP_LOGCAT_TIMEOUT"
        try:
            guest = subprocess.run([self.adb, "-s", SERIAL, "logcat", "-d", "-v", "epoch"],
                                   capture_output=True, timeout=30)
            retained, truncated = retained_logcat(guest.stdout)
            (self.out / "owned-guest-logcat.txt").write_bytes(retained)
            self.report["guestLogcatFullBytes"] = len(guest.stdout)
            self.report["guestLogcatFullSha256"] = hashlib.sha256(guest.stdout).hexdigest()
            self.report["guestLogcatRetainedSha256"] = hashlib.sha256(retained).hexdigest()
            self.report["guestLogcatTruncatedToTail"] = truncated
        except subprocess.TimeoutExpired:
            self.report["guestLogcatUnavailableReason"] = "GUEST_LOGCAT_TIMEOUT"

    def finish_owned_video(self) -> None:
        if self.recorder is None:
            return
        try:
            self.recorder.wait(timeout=98)
        except subprocess.TimeoutExpired:
            self.recorder.terminate()
            self.report["nativeVideoUnavailableReason"] = "OWNED_SCREENRECORD_DEADLINE"
            return
        self.report["screenrecordProcessExitCode"] = self.recorder.returncode
        movie = self.out / "SevenBuild11-native-kvm-observation.mp4"
        try:
            pulled = subprocess.run([self.adb, "-s", SERIAL, "pull", self.remote_movie, str(movie)],
                                    capture_output=True, timeout=75)
        except subprocess.TimeoutExpired:
            self.report["nativeVideoUnavailableReason"] = "OWNED_VIDEO_PULL_TIMEOUT"
            return
        if pulled.returncode != 0 or not movie.is_file() or movie.stat().st_size < 1024:
            self.report["nativeVideoUnavailableReason"] = "OWNED_SCREENRECORD_PULL_FAILED_OR_EMPTY"
            return
        with movie.open("rb") as stream:
            header = stream.read(16)
        if header[4:8] != b"ftyp":
            self.report["nativeVideoUnavailableReason"] = "PULLED_VIDEO_NOT_MP4"
            return
        self.report["nativeVideoCandidate"] = {"file": movie.name,
                                                 "bytes": movie.stat().st_size,
                                                 "sha256": digest(movie),
                                                 "originalScreenrecord": True}
        if self.recorder.returncode != 0:
            self.report["nativeVideoUnavailableReason"] = "OWNED_SCREENRECORD_NONZERO_EXIT"
            return
        try:
            duration_probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(movie)],
                capture_output=True, timeout=25)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self.report["nativeVideoUnavailableReason"] = "FFPROBE_UNAVAILABLE_OR_TIMEOUT"
            return
        (self.out / "owned-video-ffprobe.stdout.txt").write_bytes(duration_probe.stdout)
        (self.out / "owned-video-ffprobe.stderr.txt").write_bytes(duration_probe.stderr)
        try:
            duration = float(duration_probe.stdout.decode("utf-8", "replace").strip())
        except ValueError:
            duration = float("nan")
        self.report["nativeVideoCandidate"]["durationSeconds"] = duration if math.isfinite(duration) else None
        if duration_probe.returncode != 0 or not math.isfinite(duration) or duration < 85 or duration > 100:
            self.report["nativeVideoUnavailableReason"] = "PULLED_SCREENRECORD_DURATION_NOT_85_TO_100_SECONDS"
            return
        self.report["nativeVideo"] = {"file": movie.name, "bytes": movie.stat().st_size,
                                       "sha256": digest(movie), "durationSeconds": duration,
                                       "minimumAcceptedDurationSeconds": 85,
                                       "originalScreenrecord": True,
                                       "physicalDevice": False}

    def stop_owned_emulator(self) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            try:
                owner = subprocess.run([self.adb, "-s", SERIAL, "emu", "avd", "name"],
                                       capture_output=True, timeout=12)
                lines = owner.stdout.decode("utf-8", "replace").splitlines()
                if owner.returncode == 0 and lines and lines[0].strip() == self.avd_name:
                    subprocess.run([self.adb, "-s", SERIAL, "emu", "kill"],
                                   capture_output=True, timeout=12)
                    self.report["ownedEmulatorConsoleNameVerifiedBeforeKill"] = True
            except subprocess.TimeoutExpired:
                self.report["ownedEmulatorConsoleNameVerifiedBeforeKill"] = False
            try:
                self.proc.wait(timeout=18)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGTERM)
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                    self.proc.wait(timeout=5)
        self.report["ownedEmulatorStopped"] = self.proc.poll() is not None
        self.report["ownedEmulatorExitCode"] = self.proc.poll()
        if self.bootlog_file is not None:
            self.bootlog_file.close()

    def cleanup(self) -> None:
        for name, action in (("logcat", self.collect_final_logcat),
                             ("video", self.finish_owned_video),
                             ("emulator", self.stop_owned_emulator)):
            try:
                action()
            except Exception as error:
                self.report.setdefault("cleanupErrors", []).append({
                    "phase": name, "type": type(error).__name__, "message": str(error)[:500]})
            self.save()

    def run(self) -> None:
        failure: Exception | None = None
        try:
            self.verify_sdk_and_apk()
            self.create_owned_avd()
            self.boot_owned_emulator()
            self.set_owned_720p_size()
            self.install_and_launch()
            _, _, title_frame, title_box = self.wait_visible_start()
            self.start_owned_video()
            self.tap_visible_start_once(title_frame, title_box)
            core_hud = self.wait_gameplay_hud()
            if core_hud is not None:
                core_image, _, core_frame = core_hud
                self.maybe_swipe_observed_joystick(core_image, core_frame)
            self.observe_world()
            self.report["nativeRuntimeReady"] = True
            self.report["status"] = "NATIVE_BUILD11_WORLD_READY_AND_GAMEPLAY_HUD_OBSERVED"
            self.save()
        except Exception as error:
            failure = error
            self.report["status"] = "FAILED_NATIVE_OBSERVATION"
            self.report["errorType"] = type(error).__name__
            self.report["error"] = str(error)[:1000]
            self.report["ownedEmulatorExitAtFailure"] = self.proc.poll() if self.proc else None
            self.save()
        finally:
            self.cleanup()
        if failure is not None:
            raise failure
        if "nativeVideo" not in self.report or not self.report.get("ownedEmulatorStopped"):
            self.report["status"] = "FAILED_EVIDENCE_OR_OWNED_EMULATOR_FINALIZATION"
            self.save()
            raise RuntimeError("Native runtime observed but original video or owned emulator cleanup failed")
        self.save()
        print(self.report["status"], flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 1:
        Probe().run()
    else:
        raise SystemExit("Usage: python run_probe.py [--self-test]")
