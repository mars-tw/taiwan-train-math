"""Retain bounded, sanitized native CI failure evidence from this run only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

SOURCE_SHA = "a5cc913f566189d13ecf39b4229848fec8a43df1"


def sanitized(line: str) -> str:
    line = re.sub(r"/(?:Users|home|private|var)/[^\s\"'<>]+", "<runner-path>", line)
    line = re.sub(r"https?://[^\s\"'<>]+", "<url>", line)
    line = re.sub(r"(?i)\b(?:authorization|token|password|secret)\s*[:=]\s*\S+", "<redacted>", line)
    return line.replace("\x00", " ").strip()[:400]


def excerpt(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        return {"present": False, "selectedLines": []}
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 256 * 1024))
        lines = stream.read().decode("utf-8", "replace").splitlines()
    selected = []
    for line in lines:
        if not re.search(r"SCRIPT ERROR:|Parse Error:|ERROR:|export.*fail|failed|exception|fatal", line, re.I):
            continue
        line = sanitized(line)
        if line and line not in selected:
            selected.append(line)
        if len(selected) >= 35:
            break
    tail = [value for value in (sanitized(line) for line in lines[-30:]) if value]
    return {"present": True, "bytes": path.stat().st_size, "selectedLines": selected,
            "tailLines": tail,
            "rawLogUploaded": False}


def receipt_status(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        return {"present": False}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return {"present": True, "status": value.get("status"), "sourceSha": value.get("sourceSha")}
    except (OSError, UnicodeError, ValueError, TypeError):
        return {"present": True, "readable": False}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("android", "ios"):
        raise SystemExit("Usage: diagnose_export.py android|ios")
    kind = sys.argv[1]
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        raise SystemExit("Original manual Actions run required")
    out = workspace / "output" / ("seven-build14-" + kind)
    out.mkdir(parents=True, exist_ok=True)
    report = {"schemaVersion": 1, "kind": kind, "sourceCommit": SOURCE_SHA,
              "ciCommit": os.environ.get("GITHUB_SHA"), "runId": os.environ.get("GITHUB_RUN_ID"),
              "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
              "storeUploadPerformed": False, "physicalDeviceTested": False,
              "packagesVerified": False, "currentRunFailure": True}
    if kind == "android":
        report["stepOutcomes"] = {key: os.environ.get(key + "_OUTCOME", "unknown")
                                  for key in ("TOOLCHAIN", "TESTS", "EXPORT", "INDEPENDENT", "DRAFT")}
        source_receipt = workspace / "seven-source/deliverables/native/android-verification.json"
        report["nativeExportReceipt"] = receipt_status(source_receipt)
        destination = out / "early-failure.json"
    else:
        native = workspace / "seven-source/deliverables/native"
        report["stepOutcomes"] = {key: os.environ.get(key + "_OUTCOME", "unknown")
                                  for key in ("IOS_EXPORT", "IOS_SOURCE", "IOS_SIM", "IOS_SIGN", "IOS_DRAFT")}
        report["importLog"] = excerpt(native / "import.log")
        report["iosExportLog"] = excerpt(native / "ios-export.log")
        project = native / "ios/SevenDistrict.xcodeproj"
        pck = native / "ios/SevenDistrict.pck"
        report["xcodeProjectPresentAtFailure"] = project.is_dir()
        report["pckPresentAtFailure"] = pck.is_file()
        source_receipt = native / "ios-verification.json"
        report["nativeExportReceipt"] = receipt_status(source_receipt)
        destination = out / "early-export-failure.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
