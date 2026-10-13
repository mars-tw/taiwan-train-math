"""Package bounded Seven build 13 startup evidence, including failed probes.

The checked source and diagnostic tools stay pinned. Upload is opt-in and
one-shot; an uncertain outcome must be inspected in the draft Release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import zipfile

REPO = "mars-tw/taiwan-train-math"
TAG = "seven-build13-ios-qa-20261013"
RELEASE_ID = 411789919
SOURCE_COMMIT = "b9377588c91b95bba81e98c343e51886f3d38b01"
SOURCE_PIN = "b975e22cae4e7f7259e76b5b71e3dce5400a5739e6599a428b09d20015d81e1b"
PCK_SHA256 = "adb2466826ce250b8b357b706b3520c9e69792a2fceb06da5bbd3f724a9f9439"
VERIFIER_SHA256 = "4aefa929be7e149e6006f068fd32fa8b1832f5fab42ac66129ab92bc59a95eb0"
SIGNED_RUN_ID = 38417996013
SIGNED_IPA_SHA256 = "75d348b547cc128643f8a2c7235dc28d55756cb5c087654cbd919e61450c16c8"
SIGNED_EVIDENCE_SHA256 = "500e29b06681bdd071d8c423c70f19d8ee35402fc7fecea56585f03105db8887"
SIGNED_EVIDENCE_ASSET_ID = 637418576
MOMENTS = ("iphone-cold", "iphone-relaunch", "ipad-cold", "ipad-relaunch")
SHOT = re.compile(r"(iphone|ipad)-(cold|relaunch)-(t(?:30|60|120|180)|title)\.png")


def fail(message: str) -> None:
    raise ValueError(message)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: pathlib.Path) -> dict:
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= 1024 * 1024:
        fail("Missing or unsafe diagnostic JSON")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("Invalid diagnostic JSON object")
    return value


def require_input(stage: pathlib.Path, commit: str) -> dict:
    if sha256(stage / "SHA256SUMS") != SOURCE_PIN:
        fail("Original source SHA256SUMS pin differs")
    metadata = read_json(stage / "seven-district-reckoning-build13-source-verification.json")
    if (metadata.get("sourceCommit"), metadata.get("nativeBuild"), metadata.get("pckSha256"),
        metadata.get("sourceFiles")) != (SOURCE_COMMIT, 13, PCK_SHA256, 47):
        fail("Original source identity differs")
    provenance = read_json(stage / "diagnostic-provenance.json")
    if (provenance.get("repository"), provenance.get("releaseTag"), provenance.get("releaseId"),
        provenance.get("sourcePin"), provenance.get("sourceCommit"),
        provenance.get("signedRunId"), provenance.get("signedIpaSha256"),
        provenance.get("signedEvidenceSha256"), provenance.get("signedEvidenceAssetId"),
        provenance.get("captureToolsCommit")) != (REPO, TAG, RELEASE_ID, SOURCE_PIN, SOURCE_COMMIT,
                                                  SIGNED_RUN_ID, SIGNED_IPA_SHA256,
                                                  SIGNED_EVIDENCE_SHA256, SIGNED_EVIDENCE_ASSET_ID, commit):
        fail("Diagnostic source/tool provenance differs")
    tools = provenance.get("captureToolSha256")
    if not isinstance(tools, dict) or set(tools) != {
            "scripts/ci_seven_ios_build13_export.sh", "scripts/ci_seven_build13_readiness.py",
            "scripts/ci_seven_build13_diagnostic_package.py", "scripts/ci_verify_seven_build13.py"}:
        fail("Exact diagnostic tool hash set required")
    if tools["scripts/ci_verify_seven_build13.py"] != VERIFIER_SHA256 or any(
            not re.fullmatch(r"[0-9a-f]{64}", item) for item in tools.values()):
        fail("Diagnostic tool hash record invalid")
    return provenance


def collect(stage: pathlib.Path, out: pathlib.Path, commit: str, capture_outcome: str) -> tuple[dict, dict[str, pathlib.Path]]:
    if capture_outcome not in ("success", "failure"):
        fail("Explicit capture step outcome required")
    provenance = require_input(stage, commit)
    source = read_json(out / "source-verification.json")
    if (source.get("projectId"), source.get("build"), source.get("sourceFiles"),
        source.get("pckSha256"), source.get("sourceVerified")) != (
            "seven-district-reckoning", 13, 47, PCK_SHA256, True):
        fail("Original extracted source receipt differs")
    diagnostic = out / "diagnostic"
    files: dict[str, pathlib.Path] = {
        "source-verification.json": out / "source-verification.json",
        "source-metadata.json": stage / "seven-district-reckoning-build13-source-verification.json",
        "diagnostic-provenance.json": stage / "diagnostic-provenance.json",
    }
    for name in ("source-verification.json", "simulator-verification.json", "simulator-architecture.json",
                 "diagnostic-summary.json", "diagnostic-failure.json", "sim-build-failure.json"):
        path = diagnostic / name
        if path.is_file() and not path.is_symlink():
            files["diagnostic/" + name] = path
    build_failure_path = diagnostic / "sim-build-failure.json"
    if build_failure_path.is_file():
        build_failure = read_json(build_failure_path)
        diagnostics = build_failure.get("diagnostics")
        if (build_failure.get("projectId"), build_failure.get("phase"),
            build_failure.get("rawLogsUploaded"), build_failure.get("storeUploadPerformed")) != (
                "seven-district-reckoning", "sim-build", False, False):
            fail("Unsigned Simulator build failure receipt differs")
        if (not isinstance(diagnostics, list) or len(diagnostics) > 20 or
            any(not isinstance(line, str) or len(line) > 500 for line in diagnostics)):
            fail("Simulator build diagnostics exceed the safe bound")
    summary_path = diagnostic / "diagnostic-summary.json"
    failure_path = diagnostic / "diagnostic-failure.json"
    if capture_outcome == "success":
        summary = read_json(summary_path)
        if (summary.get("projectId"), summary.get("build"), summary.get("sourcePckSha256"),
            summary.get("uiReady"), summary.get("appleSecretsUsed"), summary.get("storeUploadPerformed")) != (
                "seven-district-reckoning", 13, PCK_SHA256, False, False, False):
            fail("Completed diagnostic summary differs")
    else:
        if not failure_path.is_file():
            diagnostic.mkdir(parents=True, exist_ok=True)
            failure_path.write_text(json.dumps({"projectId": "seven-district-reckoning", "phase": "diagnose",
                "failureCode": "CAPTURE_STEP_FAILED_WITHOUT_DETAIL", "rawLogsPublished": False,
                "appleSecretsUsed": False, "storeUploadPerformed": False}, indent=2) + "\n", encoding="utf-8")
            files["diagnostic/diagnostic-failure.json"] = failure_path
        failure = read_json(failure_path)
        if (failure.get("projectId"), failure.get("phase"), failure.get("rawLogsPublished"),
            failure.get("appleSecretsUsed"), failure.get("storeUploadPerformed")) != (
                "seven-district-reckoning", "diagnose", False, False, False):
            fail("Failure receipt safety fields differ")
        if not re.fullmatch(r"[A-Z0-9_]{3,80}", str(failure.get("failureCode", ""))):
            fail("Failure receipt code is not bounded")
    readiness = diagnostic / "readiness"
    receipts = []
    for moment in MOMENTS:
        path = readiness / (moment + ".json")
        if not path.is_file():
            if capture_outcome == "success":
                fail("Successful capture requires all four moment receipts")
            continue
        receipt = read_json(path)
        if (receipt.get("projectId"), receipt.get("build"), receipt.get("moment"),
            receipt.get("uiReady"), receipt.get("rawConsolePublished"),
            receipt.get("storeUploadPerformed")) != (
                "seven-district-reckoning", 13, moment, False, False, False):
            fail("Typed readiness receipt differs")
        files["diagnostic/readiness/" + path.name] = path
        receipts.append(receipt)
    screenshot_records = []
    if readiness.is_dir():
        for path in sorted(readiness.glob("*.png")):
            if not SHOT.fullmatch(path.name) or path.is_symlink() or not 0 < path.stat().st_size <= 20 * 1024**2:
                fail("Unsafe bounded diagnostic screenshot")
            with path.open("rb") as stream:
                header = stream.read(26)
            if len(header) != 26 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
                fail("Diagnostic screenshot is not PNG")
            width, height = struct.unpack(">II", header[16:24])
            screenshot_records.append({"file": path.name, "width": width, "height": height,
                                       "bytes": path.stat().st_size, "sha256": sha256(path)})
            files["diagnostic/readiness/" + path.name] = path
    if len(screenshot_records) > 20 or len(files) > 32 or sum(path.stat().st_size for path in files.values()) > 450 * 1024**2:
        fail("Diagnostic evidence bound exceeded")
    manifest = {"repository": REPO, "releaseTag": TAG, "releaseId": RELEASE_ID,
                "releaseDraft": True, "projectId": "seven-district-reckoning",
                "version": "1.0.0", "build": 13, "sourceCommit": SOURCE_COMMIT,
                "sourcePin": SOURCE_PIN, "pckSha256": PCK_SHA256,
                "signedRunId": SIGNED_RUN_ID, "signedIpaSha256": SIGNED_IPA_SHA256,
                "signedEvidenceSha256": SIGNED_EVIDENCE_SHA256,
                "signedEvidenceAssetId": SIGNED_EVIDENCE_ASSET_ID,
                "captureToolsCommit": commit, "captureToolSha256": provenance["captureToolSha256"],
                "captureStepOutcome": capture_outcome,
                "diagnosticStatus": "CAPTURE_COMPLETED_UI_PENDING" if capture_outcome == "success" else "CAPTURE_FAILED_EVIDENCE",
                "momentReceiptCount": len(receipts), "screenshots": screenshot_records,
                "uiReady": False, "visualReviewPending": True, "appleSecretsUsed": False,
                "physicalDeviceTested": False, "storeUploadPerformed": False}
    return manifest, files


def release() -> dict:
    result = subprocess.run(["gh", "api", "--method", "GET", f"repos/{REPO}/releases/{RELEASE_ID}"],
                            capture_output=True, timeout=60)
    if result.returncode:
        fail("Draft Release read failed; raw output withheld")
    value = json.loads(result.stdout)
    if (value.get("id"), value.get("tag_name"), value.get("draft")) != (RELEASE_ID, TAG, True):
        fail("Original draft Release identity/state changed")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--capture-outcome", choices=["success", "failure"], required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--upload", action="store_true", help="One-shot upload after reviewed manual dispatch")
    args = parser.parse_args()
    if not re.fullmatch(r"[1-9][0-9]*", args.run_id) or not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        fail("Exact run ID and capture tools commit required")
    stage, out = args.input.resolve(), args.output.resolve()
    manifest, files = collect(stage, out, args.commit, args.capture_outcome)
    manifest["runId"] = args.run_id
    descriptors = [{"name": name, "bytes": path.stat().st_size, "sha256": sha256(path)}
                   for name, path in sorted(files.items())]
    manifest["entries"] = descriptors
    manifest_path = out / "diagnostic-payload-manifest.json"
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    files[manifest_path.name] = manifest_path
    evidence = out / f"seven-build13-readiness-{args.run_id}.zip"
    with zipfile.ZipFile(evidence, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as zipped:
        for name, path in sorted(files.items()):
            zipped.write(path, name)
    with zipfile.ZipFile(evidence) as zipped:
        if len(zipped.namelist()) != len(files) or set(zipped.namelist()) != set(files):
            fail("Diagnostic ZIP members differ")
        for name, path in files.items():
            if zipped.getinfo(name).file_size != path.stat().st_size:
                fail("Diagnostic ZIP member bytes differ")
            digest = hashlib.sha256()
            with zipped.open(name) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != sha256(path):
                fail("Diagnostic ZIP member SHA differs")
    receipt = {"status": manifest["diagnosticStatus"], "asset": evidence.name,
               "bytes": evidence.stat().st_size, "sha256": sha256(evidence),
               "uiReady": False, "storeUploadPerformed": False}
    if not args.upload:
        print(json.dumps({**receipt, "uploadPerformed": False}, indent=2))
        return
    if (os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_REF"),
        os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_SHA")) != (
            REPO, "refs/heads/main", args.run_id, args.commit) or not os.environ.get("GH_TOKEN"):
        fail("Only the exact trusted GitHub run may upload")
    before = release()
    if evidence.name in {item.get("name") for item in before.get("assets", [])}:
        fail("This exact-run diagnostic asset already exists")
    journal = out / "diagnostic-upload-once.json"
    with journal.open("x", encoding="utf-8") as stream:
        json.dump({"releaseId": RELEASE_ID, "runId": args.run_id, "attempt": "ONE_SHOT",
                   "asset": evidence.name, "bytes": evidence.stat().st_size,
                   "sha256": receipt["sha256"]}, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    result = subprocess.run(["gh", "release", "upload", TAG, str(evidence), "--repo", REPO],
                            capture_output=True, timeout=900)
    if result.returncode:
        fail("Diagnostic upload failed or outcome uncertain; inspect draft before retry")
    after = release()
    remote = next((item for item in after.get("assets", []) if item.get("name") == evidence.name), None)
    if (not remote or remote.get("state") != "uploaded" or remote.get("size") != evidence.stat().st_size
        or remote.get("digest") != "sha256:" + receipt["sha256"]):
        fail("Diagnostic asset readback incomplete; inspect draft before retry")
    print(json.dumps({**receipt, "uploadPerformed": True}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, json.JSONDecodeError, subprocess.TimeoutExpired,
            zipfile.BadZipFile) as error:
        sys.exit(f"Seven diagnostic package stopped: {error}")
