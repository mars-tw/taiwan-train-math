#!/usr/bin/env python3
"""Store one verified Train Math build in an unpublished draft Release.

The input is the signed IPA produced in this same Actions run. Only the
explicitly listed public receipts and simulator captures enter the ZIP.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
SIGNED = OUTPUT / "ios-store"
SOURCE = OUTPUT / "ios-store-source"
SIMULATOR = OUTPUT / "native-artifacts" / "ios"
REPOSITORY = "mars-tw/taiwan-train-math"
APP_ID = "tw.mars.trainmath"
VERSION = "1.0.0"
BUILD = "2"


def stop(message):
    raise SystemExit(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_file(path, parent, limit):
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(parent.resolve()):
        stop(f"Missing or linked public input: {path.name}")
    size = path.stat().st_size
    if not 0 < size <= limit:
        stop(f"Invalid public input size: {path.name}")
    return {"name": path.name, "bytes": size, "sha256": sha256(path)}


def png_dimensions(path):
    with path.open("rb") as stream:
        header = stream.read(26)
    if len(header) != 26 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        stop(f"Invalid simulator PNG: {path.name}")
    width, height = struct.unpack(">II", header[16:24])
    if not 700 <= width <= 4000 or not 1000 <= height <= 4000:
        stop(f"Unexpected simulator geometry: {path.name}")
    return width, height


def run_gh(*args, timeout=120):
    result = subprocess.run(["gh", *args], capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        stop("GitHub draft Release operation failed or is uncertain; inspect the run tag before retrying")
    return result.stdout


def publish_upload_result():
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    source_sha = os.environ.get("GITHUB_SHA", "")
    outcome = os.environ.get("APPLE_UPLOAD_STEP_OUTCOME", "")
    if (os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
            or not re.fullmatch(r"[1-9][0-9]*", run_id)
            or not re.fullmatch(r"[0-9a-f]{40}", source_sha)
            or os.environ.get("APPROVED_SOURCE_SHA") != source_sha
            or outcome not in {"success", "failure"} or not os.environ.get("GH_TOKEN")):
        stop("Upload receipt cannot be tied to the approved source and exact run")
    tag = f"trainmath-1.0.0-b2-{run_id}"
    ipa = SIGNED / "TrainMath.ipa"
    verification_path = SIGNED / "verification.json"
    evidence = SIGNED / f"trainmath-1.0.0-b2-evidence-{run_id}.zip"
    for path, limit in ((ipa, 240 * 1024**2), (verification_path, 1024**2), (evidence, 250 * 1024**2)):
        checked_file(path, SIGNED, limit)
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    if (verification.get("bundleId"), verification.get("marketingVersion"), verification.get("buildNumber"),
            verification.get("sourceRun"), verification.get("sourceSha"), verification.get("ipaSha256")) != (APP_ID, VERSION, BUILD, run_id, source_sha, sha256(ipa)):
        stop("Signed IPA verification does not identify this exact approved run")

    def release_state():
        return json.loads(run_gh("api", "--method", "GET", f"repos/{REPOSITORY}/releases/tags/{tag}"))

    before = release_state()
    assets = [asset for asset in before.get("assets", []) if isinstance(asset, dict)]
    if (before.get("draft") is not True or before.get("tag_name") != tag or len(assets) != 1
            or assets[0].get("name") != evidence.name or assets[0].get("state") != "uploaded"
            or assets[0].get("size") != evidence.stat().st_size
            or assets[0].get("digest") != "sha256:" + sha256(evidence)):
        stop("Exact-run draft Release differs before upload receipt; inspect it")

    result_path = SIGNED / "upload-result.json"
    result = {}
    if result_path.is_file() and not result_path.is_symlink() and 0 < result_path.stat().st_size <= 1024**2:
        try:
            value = json.loads(result_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                result = value
        except (UnicodeError, ValueError):
            pass
    validation_accepted = result.get("appleValidationAccepted") is True
    command_accepted = result.get("uploadCommandAccepted") is True
    phase = result.get("failedPhase")
    failed_phase = phase if isinstance(phase, str) and phase in {"validate", "upload"} else None
    tool = result.get("uploadTool")
    if outcome == "success" and validation_accepted and command_accepted:
        status = "APPLE_UPLOAD_COMMAND_ACCEPTED_PROCESSING_UNVERIFIED"
    elif failed_phase == "validate":
        status = "APPLE_VALIDATION_FAILED"
    elif failed_phase == "upload":
        status = "APPLE_UPLOAD_OUTCOME_UNKNOWN"
    else:
        status = "APPLE_UPLOAD_NOT_VERIFIED"
    receipt = {
        "status": status, "repository": REPOSITORY, "releaseTag": tag,
        "appId": APP_ID, "version": VERSION, "build": int(BUILD),
        "sourceSha": source_sha, "approvedSourceSha": source_sha, "runId": run_id,
        "ipaSha256": verification["ipaSha256"], "uploadStepOutcome": outcome,
        "uploadTool": tool if isinstance(tool, str) and tool in {"iTMSTransporter", "altool"} else None,
        "appleValidationAccepted": validation_accepted,
        "uploadCommandAccepted": outcome == "success" and command_accepted,
        "failedPhase": failed_phase,
        "uploadOutcomeUnknown": status in {"APPLE_UPLOAD_OUTCOME_UNKNOWN", "APPLE_UPLOAD_NOT_VERIFIED"},
        "processingVerified": False, "testFlightAvailabilityVerified": False,
        "appStoreReviewApproved": False,
    }
    receipt_path = SIGNED / f"trainmath-apple-upload-result-{run_id}.json"
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    receipt_sha = sha256(receipt_path)
    summary = Path(os.environ["GITHUB_STEP_SUMMARY"])
    with summary.open("a", encoding="utf-8") as stream:
        stream.write(f"Apple upload receipt attach attempted for {tag}: {receipt_path.name}, SHA-256 {receipt_sha}. Inspect the draft Release before retrying.\n")
    run_gh("release", "upload", tag, str(receipt_path), "--repo", REPOSITORY, timeout=300)
    after = release_state()
    after_assets = [asset for asset in after.get("assets", []) if isinstance(asset, dict)]
    saved = next((asset for asset in after_assets if asset.get("name") == receipt_path.name), None)
    original = next((asset for asset in after_assets if asset.get("name") == evidence.name), None)
    if (after.get("id") != before.get("id") or after.get("draft") is not True
            or len(after_assets) != 2 or original is None
            or any(original.get(key) != assets[0].get(key) for key in ("id", "name", "state", "size", "digest"))
            or saved is None or saved.get("state") != "uploaded"
            or saved.get("size") != receipt_path.stat().st_size
            or saved.get("digest") != "sha256:" + receipt_sha):
        stop("Apple upload receipt readback is incomplete; inspect the same draft Release")
    with summary.open("a", encoding="utf-8") as stream:
        stream.write(f"Apple upload result {status} saved on draft Release {tag}; receipt SHA-256 {receipt_sha}. Processing and App Store approval remain unverified.\n")
    print("Sanitized Apple upload outcome saved on the exact-run draft Release")
    if outcome == "success" and status != "APPLE_UPLOAD_COMMAND_ACCEPTED_PROCESSING_UNVERIFIED":
        stop("Apple upload command returned success without a matching exporter receipt")


def main():
    if sys.argv[1:] == ["--upload-result"]:
        return publish_upload_result()
    if sys.argv[1:] != ["--publish"]:
        stop("Usage: archive-ios-store-release.py --publish|--upload-result")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    source_sha = os.environ.get("GITHUB_SHA", "")
    if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY or not re.fullmatch(r"[1-9][0-9]*", run_id):
        stop("Unexpected repository or run ID")
    if (not re.fullmatch(r"[0-9a-f]{40}", source_sha)
            or os.environ.get("APPROVED_SOURCE_SHA") != source_sha or not os.environ.get("GH_TOKEN")):
        stop("Approved source SHA or Release credential unavailable")
    tag = f"trainmath-1.0.0-b2-{run_id}"

    ipa = SIGNED / "TrainMath.ipa"
    verification_path = SIGNED / "verification.json"
    provenance_path = OUTPUT / "ios-store-provenance.json"
    manifest_path = SOURCE / "bundle-manifest.json"
    launch_path = SIMULATOR / "simulator-launch.json"
    archive_path = SOURCE / "TrainMath-unsigned.xcarchive.zip"
    files = {
        "TrainMath.ipa": ipa,
        "verification.json": verification_path,
        "ios-store-provenance.json": provenance_path,
        "bundle-manifest.json": manifest_path,
        "simulator-launch.json": launch_path,
    }
    limits = {"TrainMath.ipa": 240 * 1024**2,
              "verification.json": 1024**2,
              "ios-store-provenance.json": 1024**2,
              "bundle-manifest.json": 1024**2,
              "simulator-launch.json": 1024**2}
    for name, path in files.items():
        checked_file(path, path.parent, limits[name])
    checked_file(archive_path, SOURCE, 1024**3)

    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    if (verification.get("bundleId"), verification.get("marketingVersion"), verification.get("buildNumber")) != (APP_ID, VERSION, BUILD):
        stop("Signed app identity/version/build differ from build 2")
    for flag in ("signatureVerified", "profileVerified", "entitlementsVerified", "privacyVerified", "bundledResourcesVerified"):
        if verification.get(flag) is not True:
            stop(f"Missing signed IPA verification: {flag}")
    if verification.get("ipaSha256") != sha256(ipa) or verification.get("sourceSha") != source_sha or verification.get("sourceRun") != run_id:
        stop("Signed IPA hash or same-run provenance mismatch")
    if (provenance.get("sourceSha"), provenance.get("approvedSourceSha"), provenance.get("sourceRun"), provenance.get("repository"), provenance.get("sameRun")) != (source_sha, source_sha, run_id, REPOSITORY, True):
        stop("Unsigned archive was not prepared in this exact run")
    if provenance.get("manifestSha256") != sha256(manifest_path) or provenance.get("unsignedArchiveSha256") != sha256(archive_path):
        stop("Native bundle or unsigned archive differs from the pre-sign receipt")
    if manifest.get("appId") != APP_ID or manifest.get("remoteServer") is not False or verification.get("bundledResourceCount") != len(manifest.get("files", [])):
        stop("Offline native bundle receipt mismatch")
    devices = launch.get("devices", [])
    if launch.get("appId") != APP_ID or launch.get("actualSimulator") is not True or len(devices) != 2 or {device.get("kind") for device in devices} != {"iphone", "ipad"} or any(device.get("status") != "completed" for device in devices):
        stop("Same-run iPhone/iPad simulator launch is incomplete")
    for kind in ("iphone", "ipad"):
        device = next(item for item in devices if item["kind"] == kind)
        for state in ("home", "relaunch"):
            name = f"{kind}-simulator-{state}.png"
            path = SIMULATOR / name
            checked_file(path, SIMULATOR, 20 * 1024**2)
            dimensions = png_dimensions(path)
            if state == "home" and dimensions != (device.get("width"), device.get("height")):
                stop("Simulator screenshot dimensions differ from launch receipt")
            files[f"simulator/{name}"] = path

    descriptors = []
    for name, path in sorted(files.items()):
        descriptor = checked_file(path, path.parent, 240 * 1024**2)
        descriptor["name"] = name
        descriptors.append(descriptor)
    receipt = {
        "appId": APP_ID, "version": VERSION, "build": int(BUILD),
        "repository": REPOSITORY, "sourceSha": source_sha, "runId": run_id,
        "releaseTag": tag, "draftOnly": True, "storeUploadPerformedByThisStep": False,
        "physicalDeviceTested": False, "entries": descriptors,
    }
    receipt_path = SIGNED / "release-payload-manifest.json"
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    files[receipt_path.name] = receipt_path
    evidence = SIGNED / f"trainmath-1.0.0-b2-evidence-{run_id}.zip"
    with zipfile.ZipFile(evidence, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
        for name, path in sorted(files.items()):
            bundle.write(path, name)
    with zipfile.ZipFile(evidence) as bundle:
        if set(bundle.namelist()) != set(files) or len(bundle.namelist()) != len(files):
            stop("Evidence ZIP member set changed")
        for name, path in files.items():
            if bundle.getinfo(name).file_size != path.stat().st_size:
                stop("Evidence ZIP member length differs")
            with bundle.open(name) as data:
                digest = hashlib.sha256()
                for block in iter(lambda: data.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != sha256(path):
                stop("Evidence ZIP member hash differs")
    if evidence.stat().st_size > 250 * 1024**2:
        stop("Evidence ZIP exceeds draft Release asset limit")
    evidence_sha = sha256(evidence)

    notes = SIGNED / "release-notes.txt"
    notes.write_text(f"Private build 2 review artifact for {APP_ID}.\nSource: {source_sha}\nActions run: {run_id}\nNo App Store submission or physical-device approval is claimed by this Release.\n", encoding="utf-8")
    summary = Path(os.environ["GITHUB_STEP_SUMMARY"])
    with summary.open("a", encoding="utf-8") as stream:
        stream.write(f"Train Math build 2 draft Release create attempted: {tag}; ZIP SHA-256 {evidence_sha}. Check this tag before rerunning.\n")
    run_gh("release", "create", tag, str(evidence), "--repo", REPOSITORY, "--draft",
           "--target", source_sha, "--title", f"Train Math 1.0.0 build 2 ({run_id})",
           "--notes-file", str(notes), timeout=900)
    release = json.loads(run_gh("api", "--method", "GET", f"repos/{REPOSITORY}/releases/tags/{tag}"))
    assets = [asset for asset in release.get("assets", []) if isinstance(asset, dict)]
    if release.get("draft") is not True or release.get("tag_name") != tag or len(assets) != 1:
        stop("Draft Release identity or asset list changed; inspect before retrying")
    asset = assets[0]
    if asset.get("name") != evidence.name or asset.get("state") != "uploaded" or asset.get("size") != evidence.stat().st_size or asset.get("digest") != "sha256:" + evidence_sha:
        stop("Draft Release readback digest differs; inspect before retrying")
    with summary.open("a", encoding="utf-8") as stream:
        stream.write(f"Draft Release verified: {release.get('html_url')}; asset {evidence.name}, {evidence.stat().st_size} bytes, SHA-256 {evidence_sha}.\n")
    print("Same-run signed IPA and public QA receipts saved to a verified draft Release; no Apple upload by this step")


if __name__ == "__main__":
    main()
