"""Bounded, unsigned iOS Simulator startup observation for Seven build 12.

Only typed SEVEN_STARTUP/SEVEN_TITLE facts and real PNG hashes leave this
process. Raw console output remains private in memory and is never published.
"""
from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import math
import os
import pathlib
import re
import select
import struct
import subprocess
import sys
import time

APP_ID = "tw.mars.sevendistrictreckoning"
SAMPLES = (30, 60, 120, 180)
MAX_CONSOLE_BYTES = 10 * 1024 * 1024
MAX_LINE = 512
MAX_MARKERS = 128
PHASES = {"first_frame", "base_world", "actors", "district_life", "content_world",
          "urban_detail", "contacts", "expansion_terrain", "bindings", "core_ready",
          "expansion", "taiwan_world", "world_ready"}
EVENTS = {"font_load_begin", "font_load_end", "begin", "first_frame_wait",
          "first_frame_drawn", "first_frame_headless_not_rendered", "batch", "phase",
          "core_ready", "complete"}


def typed_marker(line: str) -> dict | None:
    if len(line) > MAX_LINE:
        return None
    if line.startswith("SEVEN_STARTUP "):
        try:
            value = json.loads(line[len("SEVEN_STARTUP "):])
        except json.JSONDecodeError:
            return None
        if not isinstance(value, dict):
            return None
        elapsed, items = value.get("elapsed_ms"), value.get("items")
        if (value.get("phase") not in PHASES or value.get("event") not in EVENTS
            or type(elapsed) not in (int, float) or not math.isfinite(elapsed)
            or not 0 <= elapsed <= 3600000 or type(items) is not int or not 0 <= items <= 1000000
            or type(value.get("ready")) is not bool):
            return None
        record = {"kind": "startup", "event": value["event"], "phase": value["phase"],
                  "elapsedMs": elapsed, "items": items, "ready": value["ready"]}
        for field in ("render_frames_drawn", "render_3d_draw_calls"):
            number = value.get(field)
            if type(number) is int and 0 <= number <= 100000000:
                record[field] = number
        for field in ("loading_layer_visible", "owner_3d_visibility_suspended"):
            boolean = value.get(field)
            if type(boolean) is bool:
                record[field] = boolean
        return record
    if line.startswith("SEVEN_TITLE "):
        try:
            value = json.loads(line[len("SEVEN_TITLE "):])
        except json.JSONDecodeError:
            return None
        if (not isinstance(value, dict) or value.get("menu") != "title"
            or value.get("loading_layer_visible") is not False
            or type(value.get("world_render_suspended")) is not bool):
            return None
        return {"kind": "title", "menu": "title", "loadingLayerVisible": False,
                "worldRenderSuspended": value["world_render_suspended"]}
    return None


def screenshot(device: str, path: pathlib.Path) -> dict:
    if path.exists() or path.is_symlink():
        raise ValueError("Diagnostic screenshot path already exists")
    result = subprocess.run(["xcrun", "simctl", "io", device, "screenshot", "--type=png", str(path)],
                            capture_output=True, timeout=120)
    if result.returncode or not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size < 20 * 1024**2:
        raise ValueError("Actual Simulator screenshot failed")
    with path.open("rb") as stream:
        header = stream.read(26)
    if len(header) != 26 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("Simulator screenshot is not PNG")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    width, height = struct.unpack(">II", header[16:24])
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": digest,
            "width": width, "height": height, "rgbNoAlpha": header[25] == 2}


def observe(device: str, moment: str, output: pathlib.Path) -> dict:
    if not re.fullmatch(r"[A-Fa-f0-9]{8}(?:-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}", device):
        raise ValueError("Fresh owned Simulator UUID required")
    output.mkdir(parents=True, exist_ok=True)
    receipt = output / f"{moment}.json"
    if receipt.exists():
        raise ValueError("Diagnostic receipt already exists")
    launched = time.monotonic()
    process = subprocess.Popen(["xcrun", "simctl", "launch", "--console-pty", device, APP_ID],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, bufsize=0)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    line = ""
    overlong = False
    total_bytes = 0
    rejected = 0
    dropped_markers = 0
    markers: list[dict] = []
    shots: list[dict] = []
    title_seen_at: float | None = None
    next_sample = 0
    console_overflow = False
    try:
        while True:
            elapsed = time.monotonic() - launched
            if next_sample < len(SAMPLES) and elapsed >= SAMPLES[next_sample]:
                second = SAMPLES[next_sample]
                shot = screenshot(device, output / f"{moment}-t{second}.png")
                shot["elapsedSeconds"] = round(time.monotonic() - launched, 3)
                shots.append(shot)
                next_sample += 1
            if title_seen_at is not None and elapsed >= title_seen_at + 2:
                shot = screenshot(device, output / f"{moment}-title.png")
                shot["elapsedSeconds"] = round(time.monotonic() - launched, 3)
                shots.append(shot)
                break
            if elapsed >= SAMPLES[-1] or console_overflow:
                break
            ready, _, _ = select.select([process.stdout], [], [],
                                        0 if process.poll() is not None else min(0.25, SAMPLES[-1] - elapsed))
            if not ready:
                if process.poll() is not None:
                    break
                continue
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                if process.poll() is not None:
                    break
                continue
            total_bytes += len(chunk)
            if total_bytes > MAX_CONSOLE_BYTES:
                console_overflow = True
                continue
            for character in decoder.decode(chunk):
                if character == "\n":
                    candidate = line.rstrip("\r")
                    if candidate.startswith(("SEVEN_STARTUP ", "SEVEN_TITLE ")):
                        marker = None if overlong else typed_marker(candidate)
                        if marker is None:
                            rejected += 1
                        else:
                            if len(markers) >= MAX_MARKERS:
                                markers.pop(0)
                                dropped_markers += 1
                            markers.append(marker)
                            if marker["kind"] == "title":
                                title_seen_at = time.monotonic() - launched
                    line = ""
                    overlong = False
                elif not overlong:
                    if len(line) < MAX_LINE:
                        line += character
                    else:
                        overlong = True
        console_exit_at_end = process.poll()
        console_attached_at_end = console_exit_at_end is None
    finally:
        # End only the app on this fresh owned Simulator, then close its console.
        subprocess.run(["xcrun", "simctl", "terminate", device, APP_ID], capture_output=True, timeout=60)
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.stdout:
            process.stdout.close()
    title_frame_captured = any(shot["file"] == f"{moment}-title.png" for shot in shots)
    milestone = title_seen_at is not None and title_frame_captured and not console_overflow
    result = {"projectId": "seven-district-reckoning", "appId": APP_ID,
              "version": "1.0.0", "build": 12, "device": device, "moment": moment,
              "observer": "own-game-simctl-console-pty", "maxWaitSeconds": SAMPLES[-1],
              "sampleSeconds": list(SAMPLES), "elapsedSeconds": round(time.monotonic() - launched, 3),
              "titleMarkerSeen": title_seen_at is not None,
              "titleMarkerAtSeconds": round(title_seen_at, 3) if title_seen_at is not None else None,
              "titleFrameCaptured": title_frame_captured,
              "titleMilestoneObserved": milestone,
              "uiReady": False,
              "diagnosticStatus": "TITLE_MARKER_WITH_FRAME" if milestone else
                                  "TITLE_MARKER_NO_FRAME" if title_seen_at is not None else
                                  "CONSOLE_LIMIT_EXCEEDED" if console_overflow else
                                  "CONSOLE_CLOSED_BEFORE_TITLE" if not console_attached_at_end else
                                  "READINESS_NOT_ESTABLISHED",
              "consoleAttachedAtEnd": console_attached_at_end,
              "consoleExitCodeAtEnd": console_exit_at_end,
              "consoleBytesObserved": total_bytes, "typedMarkers": markers,
              "rejectedMarkerLines": rejected, "droppedTypedMarkers": dropped_markers,
              "screenshots": shots,
              "rawConsolePublished": False, "visualReviewPending": True,
              "interactiveGameplayTested": False, "physicalDeviceTested": False,
              "storeUploadPerformed": False}
    receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--moment", choices=["iphone-cold", "iphone-relaunch", "ipad-cold", "ipad-relaunch"], required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = observe(args.device, args.moment, args.output.resolve())
    print(json.dumps({"moment": result["moment"], "diagnosticStatus": result["diagnosticStatus"],
                      "titleMarkerAtSeconds": result["titleMarkerAtSeconds"],
                      "screenshots": len(result["screenshots"]), "rawConsolePublished": False}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        sys.exit(f"Seven readiness diagnostic stopped: {type(error).__name__}; raw output withheld")
