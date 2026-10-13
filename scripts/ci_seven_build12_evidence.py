"""Verify one Seven District build 12 Mac run and upload one draft Release evidence ZIP.

No App Store, TestFlight, or Actions artifact API is used. An uncertain Release
upload is never retried automatically.
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
TAG = "seven-build12-ios-qa-20261013"
PROJECT = "seven-district-reckoning"
APP_ID = "tw.mars.sevendistrictreckoning"
SOURCE_COMMIT = "f6fc1155b0296f74972775a0426af25af4e04416"
PCK_SHA256 = "d4c19f09bd7f06c038c61ded32d3f79c5ef9f13042fb1f35b951a88443fc5bc8"
SOURCE_ZIP = "SevenDistrict-1.0.0-build12-unsigned-source.zip"
METADATA = "seven-district-reckoning-build12-source-verification.json"
HELPERS = ("ci_verify_seven_build12.py", "ci_seven_ios_build12_export.sh",
           "ci_seven_build12_evidence.py")


def fail(message: str) -> None:
    raise ValueError(message)


def digest(path: pathlib.Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def command(args: list[str], timeout: int = 120) -> bytes:
    process = subprocess.run(args, capture_output=True, timeout=timeout)
    if process.returncode:
        fail("GitHub or local verification command failed; output withheld")
    return process.stdout


def load(path: pathlib.Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1024 * 1024:
        fail("Missing or unsafe public verification record")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("Invalid public verification record")
    return value


def check_input(stage: pathlib.Path, pin: str, release_id: int) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", pin):
        fail("Invalid approved source pin")
    required = {SOURCE_ZIP, METADATA, *HELPERS}
    if {p.name for p in stage.iterdir()} != required | {"SHA256SUMS", "input-provenance.json"}:
        fail("Unexpected source staging file set")
    for path in stage.iterdir():
        if path.is_symlink() or not path.is_file():
            fail("Source stage includes a link or directory")
    sums = stage / "SHA256SUMS"
    if digest(sums) != pin:
        fail("Approved source checksum pin changed")
    expected = {}
    for line in sums.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._-]{0,150})", line)
        if not match or match[2] in expected:
            fail("Malformed source checksum record")
        expected[match[2]] = match[1]
    if set(expected) != required:
        fail("Source manifest has missing or unexpected entries")
    for name, sha in expected.items():
        target = stage / name
        maximum = 1024**3 if name == SOURCE_ZIP else 1024**2
        if not 0 < target.stat().st_size <= maximum or digest(target) != sha:
            fail("Source file changed after approved manifest")
    provenance = load(stage / "input-provenance.json")
    if (provenance.get("repository"), provenance.get("releaseTag"),
        provenance.get("releaseId"), provenance.get("releaseDraft"),
        provenance.get("checksumManifestSha256")) != (REPO, TAG, release_id, True, pin):
        fail("Source Release provenance differs")
    metadata = load(stage / METADATA)
    if (metadata.get("sourceCommit"), metadata.get("nativeBuild"),
        metadata.get("pckSha256"), metadata.get("sourceFiles")) != (
            SOURCE_COMMIT, 12, PCK_SHA256, 47):
        fail("Source metadata is not the reviewed clean build 12")
    if metadata.get("zip") != {"file": SOURCE_ZIP, "bytes": (stage / SOURCE_ZIP).stat().st_size,
                               "sha256": expected[SOURCE_ZIP]}:
        fail("Source ZIP metadata binding differs")
    return provenance


def check_receipts(stage: pathlib.Path, source: pathlib.Path, output: pathlib.Path) -> dict:
    verifier = stage / "ci_verify_seven_build12.py"
    command(["python3", str(verifier), "source", "--root", str(source),
             "--metadata", str(stage / METADATA), "--project", PROJECT,
             "--output", str(output / "source-verification-after-sign.json")], timeout=300)
    source_names = ["source-verification.json", "prepare/source-verification.json",
                    "sim/source-verification.json", "source-verification-pre-sign.json",
                    "signed/source-verification.json",
                    "source-verification-after-sign.json"]
    receipts = [load(output / name) for name in source_names]
    for receipt in receipts:
        if ((receipt.get("projectId"), receipt.get("appId"), receipt.get("version"),
             receipt.get("build"), receipt.get("sourceFiles"), receipt.get("pckSha256"),
             receipt.get("sourceVerified"), receipt.get("storeUploadPerformed")) !=
            (PROJECT, APP_ID, "1.0.0", 12, 47, PCK_SHA256, True, False)):
            fail("Source changed between extract, Mac build, and signing")
    simulator = load(output / "sim/simulator-verification.json")
    signed = load(output / "signed/verification.json")
    for receipt in (simulator, signed):
        if (receipt.get("projectId"), receipt.get("appId"), receipt.get("version"),
            receipt.get("build"), receipt.get("pckSha256"),
            receipt.get("macBuildPerformed"), receipt.get("storeUploadPerformed")) != (
                PROJECT, APP_ID, "1.0.0", 12, PCK_SHA256, True, False):
            fail("Built App or signed IPA differs from source PCK/build")
    if simulator.get("deviceBuild") is not False or "x86_64" not in simulator.get("architectures", []):
        fail("Actual x86_64 Simulator App is missing")
    if (signed.get("deviceBuild") is not True or signed.get("architectures") != ["arm64"]
        or signed.get("signatureVerified") is not True or signed.get("profileVerified") is not True
        or signed.get("requiredReasonsVerified") is not True or signed.get("appStoreApproved") is not False):
        fail("Device IPA signature, profile, or architecture is incomplete")
    ipa = output / "signed/signed.ipa"
    if (not ipa.is_file() or ipa.is_symlink() or not 0 < ipa.stat().st_size < 500 * 1024**2
        or ipa.stat().st_size != signed.get("ipaBytes") or digest(ipa) != signed.get("ipaSha256")):
        fail("Signed IPA bytes differ from the verified receipt")
    launch = load(output / "sim/simulator-launch.json")
    if (launch.get("projectId"), launch.get("actualSimulator"), launch.get("freshDevices"),
        launch.get("macBuildPerformed"), launch.get("simulatorArchitecture"),
        launch.get("storeUploadPerformed")) != (PROJECT, True, True, True, "x86_64", False):
        fail("Fresh actual Intel Simulator capture receipt is missing")
    screenshots = launch.get("screenshots")
    expected = {"sim/screenshots/iphone-cold.png": (1320, 2868),
                "sim/screenshots/iphone-relaunch.png": (1320, 2868),
                "sim/screenshots/ipad-cold.png": (2064, 2752),
                "sim/screenshots/ipad-relaunch.png": (2064, 2752)}
    if (not isinstance(screenshots, list) or len(screenshots) != 4 or
        {"sim/" + item.get("file", "") for item in screenshots if isinstance(item, dict)} != set(expected)):
        fail("Exactly four fresh iPhone/iPad screenshots are required")
    for shot in screenshots:
        name = "sim/" + shot["file"]
        file = output / name
        if (not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(output.resolve())
            or not 0 < file.stat().st_size <= 20 * 1024**2):
            fail("Missing or unsafe Simulator screenshot")
        with file.open("rb") as stream:
            head = stream.read(26)
        if len(head) != 26 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR" or head[25] != 2:
            fail("Simulator screenshot must be a decoded RGB PNG")
        dimensions = struct.unpack(">II", head[16:24])
        if (dimensions not in (expected[name], expected[name][::-1]) or
            (shot.get("width"), shot.get("height")) != dimensions or digest(file) != shot.get("sha256")):
            fail("Simulator screenshot bytes or dimensions changed")
    return {"ipaSha256": signed["ipaSha256"], "ipaBytes": signed["ipaBytes"],
            "screenshots": {"sim/" + item["file"]: item["sha256"] for item in screenshots}}


def read_release(release_id: int) -> dict:
    release = json.loads(command(["gh", "api", "--method", "GET",
                                  f"repos/{REPO}/releases/{release_id}"], timeout=60))
    if release.get("id") != release_id or release.get("tag_name") != TAG or release.get("draft") is not True:
        fail("Approved draft Release identity or state changed")
    return release


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=pathlib.Path)
    parser.add_argument("--source", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--pin", required=True)
    parser.add_argument("--release-id", required=True, type=int)
    args = parser.parse_args()
    stage, source, output = args.input.resolve(), args.source.resolve(), args.output.resolve()
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if (os.environ.get("GITHUB_REPOSITORY") != REPO or os.environ.get("GITHUB_REF") != "refs/heads/main"
        or not re.fullmatch(r"[1-9][0-9]*", run_id) or not os.environ.get("GH_TOKEN")):
        fail("Exact trusted GitHub Actions run is required")
    check_input(stage, args.pin, args.release_id)
    result = check_receipts(stage, source, output)
    release = read_release(args.release_id)
    asset_name = f"seven-build12-ios-evidence-{run_id}.zip"
    if asset_name in {item.get("name") for item in release.get("assets", [])}:
        fail("This run's draft evidence asset already exists; no overwrite")
    files = {name: output / name for name in [
        "source-verification.json", "prepare/source-verification.json",
        "sim/source-verification.json", "source-verification-pre-sign.json",
        "signed/source-verification.json",
        "source-verification-after-sign.json", "sim/simulator-verification.json",
        "sim/simulator-architecture.json", "sim/simulator-launch.json",
        "signed/verification.json", "signed/signed.ipa",
        "sim/screenshots/iphone-cold.png", "sim/screenshots/iphone-relaunch.png",
        "sim/screenshots/ipad-cold.png", "sim/screenshots/ipad-relaunch.png"]}
    files[METADATA] = stage / METADATA
    files["input-provenance.json"] = stage / "input-provenance.json"
    entries = []
    for name, path in sorted(files.items()):
        if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
            fail("Exact-run evidence member is missing or linked")
        entries.append({"name": name, "bytes": path.stat().st_size, "sha256": digest(path)})
    manifest = output / "release-payload-manifest.json"
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump({"repository": REPO, "releaseTag": TAG, "releaseId": args.release_id,
                   "releaseDraft": True, "runId": run_id, "sourceCommit": SOURCE_COMMIT,
                   "sourcePin": args.pin, "projectId": PROJECT, "version": "1.0.0",
                   "build": 12, "pckSha256": PCK_SHA256, "ipaSha256": result["ipaSha256"],
                   "screenshots": result["screenshots"], "physicalDeviceTested": False,
                   "visualReviewPending": True, "interactiveGameplayTested": False,
                   "storeUploadPerformed": False, "entries": entries}, stream, indent=2)
        stream.write("\n")
    files[manifest.name] = manifest
    evidence = output / asset_name
    with zipfile.ZipFile(evidence, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as zipped:
        for name, path in sorted(files.items()):
            zipped.write(path, name)
    with zipfile.ZipFile(evidence) as zipped:
        if len(zipped.namelist()) != len(files) or set(zipped.namelist()) != set(files):
            fail("Evidence ZIP member list differs")
        for name, path in files.items():
            info = zipped.getinfo(name)
            if info.file_size != path.stat().st_size or info.compress_type != zipfile.ZIP_STORED:
                fail("Evidence ZIP member size/compression changed")
            with zipped.open(name) as stream:
                hasher = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(block)
            if hasher.hexdigest() != digest(path):
                fail("Evidence ZIP member SHA-256 differs")
    evidence_sha = digest(evidence)
    with (output / "release-upload-once.json").open("x", encoding="utf-8") as stream:
        json.dump({"releaseId": args.release_id, "tag": TAG, "runId": run_id,
                   "attempt": "ONE_SHOT", "asset": asset_name,
                   "bytes": evidence.stat().st_size, "sha256": evidence_sha}, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with pathlib.Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(f"Seven build 12: one-shot draft Release evidence upload attempted: {asset_name} "
                         f"({evidence.stat().st_size} bytes, SHA-256 {evidence_sha}). "
                         "No App Store upload or gameplay approval. Inspect draft before retry.\n")
    try:
        command(["gh", "release", "upload", TAG, str(evidence), "--repo", REPO], timeout=900)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        fail("Draft upload failed or outcome uncertain; inspect Release before any retry")
    after = read_release(args.release_id)
    assets = {item.get("name"): item for item in after.get("assets", [])}
    asset = assets.get(asset_name)
    if (not asset or asset.get("state") != "uploaded" or asset.get("size") != evidence.stat().st_size
        or asset.get("digest") != "sha256:" + evidence_sha):
        fail("Draft Release evidence readback incomplete; inspect before retry")
    print(json.dumps({"status": "DRAFT_EVIDENCE_VERIFIED", "releaseId": args.release_id,
                      "runId": run_id, "asset": asset_name, "bytes": evidence.stat().st_size,
                      "sha256": evidence_sha, "storeUploadPerformed": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, json.JSONDecodeError, subprocess.TimeoutExpired,
            zipfile.BadZipFile) as error:
        sys.exit(f"Seven build 12 evidence stopped: {error}")
