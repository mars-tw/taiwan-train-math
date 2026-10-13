"""Preserve one verified build 14 QA bundle on a private draft Release.

This is a terminal CI step. A failed or uncertain upload is not retried here.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import zipfile

REPO = "mars-tw/taiwan-train-math"
SOURCE_SHA = "a5cc913f566189d13ecf39b4229848fec8a43df1"
APP_ID = "tw.mars.sevendistrictreckoning"
BUILD = 14


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def gh(*args: str, timeout: int = 180) -> bytes:
    try:
        result = subprocess.run(["gh", *args], capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError("GitHub draft operation timed out; provider output withheld") from None
    if result.returncode:
        raise RuntimeError("GitHub draft operation failed; provider output withheld")
    return result.stdout


def draft_by_tag(tag: str) -> list[dict]:
    for attempt in range(3):
        try:
            pages = json.loads(gh("api", "--method", "GET", "--paginate", "--slurp",
                                  f"repos/{REPO}/releases?per_page=100", timeout=90))
            return [item for page in pages for item in page if item.get("tag_name") == tag]
        except (RuntimeError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2)
    raise AssertionError("unreachable")


def context() -> tuple[str, str]:
    fields = (os.environ.get("GITHUB_ACTIONS"), os.environ.get("GITHUB_EVENT_NAME"),
              os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_REF"),
              os.environ.get("GITHUB_RUN_ATTEMPT"))
    if fields != ("true", "workflow_dispatch", REPO, "refs/heads/main", "1"):
        raise ValueError("Only one original manual main-branch Actions attempt is eligible")
    run_id, ci_sha = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[1-9][0-9]{5,15}", run_id) or not re.fullmatch(r"[0-9a-f]{40}", ci_sha):
        raise ValueError("Original run ID or workflow commit missing")
    if not os.environ.get("GH_TOKEN"):
        raise ValueError("This job needs its own contents-write GitHub token")
    return run_id, ci_sha


def android_files(workspace: Path) -> dict[str, Path]:
    source = workspace / "seven-source"
    root = source / "deliverables/native"
    receipt = json.loads((root / "android-verification.json").read_text(encoding="utf-8"))
    independent = json.loads((root / "independent-signature-check.json").read_text(encoding="utf-8"))
    if (receipt.get("sourceSha"), receipt.get("appId"), receipt.get("nativeVersion"),
            receipt.get("nativeBuild"), receipt.get("status"), receipt.get("signed"),
            receipt.get("uploaded")) != (SOURCE_SHA, APP_ID, "1.0.0", BUILD,
                                         "unsigned-android-verified", False, False):
        raise ValueError("Android export receipt is not the exact unsigned build 14")
    if (independent.get("sourceSha"), independent.get("build"),
            independent.get("apkV1RecordsPresent"), independent.get("apkV2V3SigningBlockPresent"),
            independent.get("aabJarsignerReportedUnsigned"),
            independent.get("forbiddenPermissionsPresent")) != (SOURCE_SHA, BUILD, False, False, True, False):
        raise ValueError("Independent Android signature/permission checks missing")
    files = {"native-unsigned.apk": root / "native-unsigned.apk",
             "native-unsigned.aab": root / "native-unsigned.aab",
             "android-verification.json": root / "android-verification.json",
             "independent-signature-check.json": root / "independent-signature-check.json",
             "engine-checks.json": source / "qa/engine-checks.json"}
    package_records = {entry.get("file"): entry for entry in receipt.get("packages", [])}
    if set(package_records) != {"native-unsigned.apk", "native-unsigned.aab"}:
        raise ValueError("Exact Android package pair missing")
    for name in package_records:
        path, item = files[name], package_records[name]
        if path.stat().st_size != item.get("bytes") or sha(path) != item.get("sha256"):
            raise ValueError("Android package differs from Godot inspection receipt")
    tests = json.loads(files["engine-checks.json"].read_text(encoding="utf-8"))
    if not isinstance(tests, list) or len(tests) != 19 or any(row.get("status") != "PASS" for row in tests):
        raise ValueError("Full Godot suite receipt is absent or failed")
    return files


def ios_files(workspace: Path) -> dict[str, Path]:
    out = workspace / "output/seven-build14-ios"
    source = workspace / "seven-source"
    verification = json.loads((out / "verification.json").read_text(encoding="utf-8"))
    metadata = json.loads((out / "ios-source-metadata.json").read_text(encoding="utf-8"))
    source_verification = json.loads((out / "source-verification.json").read_text(encoding="utf-8"))
    godot_export = json.loads((source / "deliverables/native/ios-verification.json").read_text(encoding="utf-8"))
    toolchain = json.loads((out / "toolchain-layout.json").read_text(encoding="utf-8"))
    sim = json.loads((out / "simulator-launch.json").read_text(encoding="utf-8"))
    ipa = out / "signed.ipa"
    if (toolchain.get("engineVersion"), toolchain.get("officialEditorExecuted"),
            toolchain.get("publisherDigestsVerified"), toolchain.get("selfContainedMarker"),
            toolchain.get("editorData"), toolchain.get("iosTemplatePresent")) != (
                "4.7.2", True, True, "beside-Godot.app", "beside-Godot.app", True):
        raise ValueError("Official macOS portable Godot template layout differs")
    if not re.fullmatch(r"[0-9a-f]{64}", toolchain.get("iosTemplateSha256", "")):
        raise ValueError("Official iOS template digest is missing")
    if (godot_export.get("sourceSha"), godot_export.get("appId"), godot_export.get("nativeVersion"),
            godot_export.get("nativeBuild"), godot_export.get("status"), godot_export.get("signed"),
            godot_export.get("uploaded")) != (SOURCE_SHA, APP_ID, "1.0.0", BUILD,
                                             "ios-xcode-source-created-not-compiled", False, False):
        raise ValueError("Godot iOS source-only export receipt differs")
    if (source_verification.get("projectId"), source_verification.get("appId"),
            source_verification.get("version"), source_verification.get("build"),
            source_verification.get("pckSha256"), source_verification.get("sourceMetadataSha256"),
            source_verification.get("sourceVerified"), source_verification.get("storeUploadPerformed")) != (
                "seven-district-reckoning", APP_ID, "1.0.0", BUILD,
                metadata.get("pckSha256"), sha(out / "ios-source-metadata.json"), True, False):
        raise ValueError("iOS source verifier receipt or metadata digest differs")
    if (verification.get("projectId"), verification.get("appId"), verification.get("version"),
            verification.get("build"), verification.get("pckSha256"),
            verification.get("signatureVerified"), verification.get("profileVerified"),
            verification.get("requiredReasonsVerified"), verification.get("storeUploadPerformed")) != (
                "seven-district-reckoning", APP_ID, "1.0.0", BUILD, metadata.get("pckSha256"),
                True, True, True, False):
        raise ValueError("iOS signature/profile/source receipt is incomplete")
    if (metadata.get("sourceCommit"), metadata.get("nativeBuild"), metadata.get("sourceFiles")) != (SOURCE_SHA, BUILD, 47):
        raise ValueError("iOS source metadata differs")
    if ipa.stat().st_size != verification.get("ipaBytes") or sha(ipa) != verification.get("ipaSha256"):
        raise ValueError("Signed IPA byte hash differs from verification")
    if (sim.get("actualSimulator"), sim.get("freshDevices"), sim.get("storeUploadPerformed")) != (True, True, False):
        raise ValueError("Fresh Simulator runtime receipt missing")
    shots = sim.get("screenshots", [])
    if not isinstance(shots, list) or len(shots) != 4:
        raise ValueError("Expected four original Simulator captures")
    files = {"signed.ipa": ipa,
             "ios-source-metadata.json": out / "ios-source-metadata.json",
             "source-verification.json": out / "source-verification.json",
             "simulator-architecture.json": out / "simulator-architecture.json",
             "simulator-verification.json": out / "simulator-verification.json",
             "simulator-launch.json": out / "simulator-launch.json",
             "verification.json": out / "verification.json",
             "toolchain-layout.json": out / "toolchain-layout.json",
             "ios-verification.json": source / "deliverables/native/ios-verification.json"}
    for shot in shots:
        name = shot.get("file", "")
        if not re.fullmatch(r"screenshots/(?:iphone|ipad)-(?:cold|relaunch)\.png", name) or name in files:
            raise ValueError("Unexpected Simulator capture name")
        path = out / name
        if sha(path) != shot.get("sha256"):
            raise ValueError("Simulator capture digest differs")
        files[name] = path
    if len(files) != 13:
        raise ValueError("Simulator capture set is duplicate or incomplete")
    return files


def make_bundle(kind: str, run_id: str, ci_sha: str, files: dict[str, Path]) -> tuple[Path, dict]:
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    tag = f"seven-build14-{kind}-qa-{run_id}"
    archive = temp / (tag + ".zip")
    if archive.exists() or archive.is_symlink():
        raise ValueError("Owned QA bundle already exists; no overwrite")
    records = []
    for name, path in sorted(files.items()):
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size < 1024**3:
            raise ValueError("Missing, linked or oversized QA output")
        records.append({"path": name, "bytes": path.stat().st_size, "sha256": sha(path)})
    manifest = {"schemaVersion": 1, "projectId": "seven-district-reckoning",
                "appId": APP_ID, "nativeVersion": "1.0.0", "nativeBuild": BUILD,
                "sourceCommit": SOURCE_SHA, "ciCommit": ci_sha, "runId": run_id,
                "kind": kind, "storeUploadPerformed": False, "physicalDeviceTested": False,
                "files": records}
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED, strict_timestamps=False) as bundle:
        for item in records:
            bundle.write(files[item["path"]], item["path"])
        bundle.writestr("bundle-manifest.json", json.dumps(manifest, indent=2) + "\n")
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None or set(bundle.namelist()) != {"bundle-manifest.json", *files}:
            raise ValueError("QA bundle contents failed local verification")
    return archive, manifest


def publish(archive: Path, manifest: dict) -> None:
    kind, run_id, ci_sha = manifest["kind"], manifest["runId"], manifest["ciCommit"]
    tag = f"seven-build14-{kind}-qa-{run_id}"
    if draft_by_tag(tag):
        raise ValueError("Draft tag already exists; uncertain prior upload is not retried")
    title = f"Seven District build 14 {kind} private QA run {run_id}"
    notes = (f"Source: {SOURCE_SHA}\nCI: {ci_sha}\nActions run: {run_id}\n"
             "QA evidence only. No Play/App Store Connect upload or physical-device approval.\n")
    digest = sha(archive)
    print(json.dumps({"status": "DRAFT_UPLOAD_PREPARED", "kind": kind, "runId": run_id,
                      "sourceSha": SOURCE_SHA, "ciSha": ci_sha,
                      "bundleBytes": archive.stat().st_size, "bundleSha256": digest,
                      "draftCreated": False, "storeUploadPerformed": False}), flush=True)
    # Exactly one create/upload mutation; a network error leaves an uncertain outcome.
    gh("release", "create", tag, str(archive), "--repo", REPO, "--draft", "--target", ci_sha,
       "--title", title, "--notes", notes, timeout=360)
    matches = draft_by_tag(tag)
    if len(matches) != 1 or matches[0].get("draft") is not True or matches[0].get("target_commitish") != ci_sha:
        raise RuntimeError("Draft Release readback identity differs")
    release = matches[0]
    assets = [item for item in release.get("assets", []) if item.get("name") == archive.name]
    if len(assets) != 1 or assets[0].get("state") != "uploaded" or assets[0].get("size") != archive.stat().st_size:
        raise RuntimeError("Draft Release asset readback differs")
    if assets[0].get("digest") not in (None, "sha256:" + digest):
        raise RuntimeError("Draft Release asset digest differs")
    readback = Path(os.environ["RUNNER_TEMP"]).resolve() / (tag + "-readback")
    if readback.exists() or readback.is_symlink():
        raise RuntimeError("Draft asset readback directory is not fresh")
    readback.mkdir()
    downloaded = readback / archive.name
    for attempt in range(3):
        try:
            gh("release", "download", tag, "--repo", REPO, "--pattern", archive.name,
               "--dir", str(readback), timeout=360)
            if (not downloaded.is_file() or downloaded.is_symlink()
                    or downloaded.stat().st_size != archive.stat().st_size
                    or sha(downloaded) != digest):
                raise RuntimeError("Draft asset download differs from locally verified bundle")
            break
        except RuntimeError:
            downloaded.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(3)
    print(json.dumps({"status": "DRAFT_RELEASE_VERIFIED", "kind": kind, "runId": run_id,
                      "sourceSha": SOURCE_SHA, "ciSha": ci_sha, "releaseId": release["id"],
                      "assetId": assets[0]["id"], "assetBytes": archive.stat().st_size,
                      "assetSha256": digest, "draft": True, "storeUploadPerformed": False}))


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("android", "ios"):
        raise SystemExit("Usage: publish_draft.py android|ios")
    kind = sys.argv[1]
    run_id, ci_sha = context()
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
    files = android_files(workspace) if kind == "android" else ios_files(workspace)
    if any(not path.resolve().is_relative_to(workspace) for path in files.values()):
        raise ValueError("QA output path leaves the owned CI workspace")
    archive, manifest = make_bundle(kind, run_id, ci_sha, files)
    publish(archive, manifest)


if __name__ == "__main__":
    main()
