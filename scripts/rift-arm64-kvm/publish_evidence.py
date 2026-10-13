"""Append one indexed Rift KVM evidence ZIP to the existing exact draft."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

from fetch_input import (APK_BYTES, APK_NAME, APK_SHA, ASSET_ID, BRANCH,
                         RELEASE_ID, REPO, TAG, read_manifest)


OWNER = "rift-arm64-kvm-r4"
MAX_EVIDENCE_BYTES = 512 * 1024 * 1024


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def gh_release() -> dict:
    result = subprocess.run(["gh", "api", f"repos/{REPO}/releases/{RELEASE_ID}"],
                            capture_output=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError("Exact Rift draft readback failed; provider output withheld")
    return json.loads(result.stdout)


def verify_release(release: dict) -> None:
    if (release.get("id") != RELEASE_ID or release.get("tag_name") != TAG
            or release.get("draft") is not True):
        raise RuntimeError("Pinned Rift QA draft identity changed")
    original = [asset for asset in release.get("assets", []) if asset.get("id") == ASSET_ID]
    if len(original) != 1:
        raise RuntimeError("Pinned original Rift APK asset missing or ambiguous")
    apk = original[0]
    if (apk.get("name") != APK_NAME or apk.get("size") != APK_BYTES
            or apk.get("digest") != "sha256:" + APK_SHA
            or apk.get("state") != "uploaded"):
        raise RuntimeError("Pinned original Rift APK asset metadata changed")


def owned_output(workspace: Path, run_id: str, head_sha: str) -> Path:
    parent = workspace / "output"
    output = parent / OWNER
    if (parent.is_symlink() or output.is_symlink()
            or not output.resolve().is_relative_to(workspace.resolve())):
        raise RuntimeError("Rift evidence output leaves trusted checkout")
    owner = {"runId": run_id, "headSha": head_sha, "owner": OWNER}
    if output.exists():
        marker = output / "owned-run.json"
        if marker.is_symlink() or not marker.is_file():
            raise RuntimeError("Preexisting Rift output lacks owned-run marker")
        if json.loads(marker.read_text(encoding="utf-8")) != owner:
            raise RuntimeError("Preexisting Rift output belongs to another run")
    else:
        output.mkdir(parents=True, exist_ok=False)
        (output / "owned-run.json").write_text(json.dumps(owner, indent=2) + "\n", encoding="utf-8")
    return output


def indexed_files(output: Path) -> tuple[list[Path], list[dict], int]:
    entries = list(output.rglob("*"))
    if any(path.is_symlink() or not path.resolve().is_relative_to(output.resolve()) for path in entries):
        raise RuntimeError("Linked or external Rift evidence entry")
    files = sorted(path for path in entries if path.is_file() and path != output / "evidence-index.json")
    total = sum(path.stat().st_size for path in files)
    if total > MAX_EVIDENCE_BYTES:
        raise RuntimeError("Rift evidence exceeds bounded 512 MiB package")
    rows = [{"path": path.relative_to(output).as_posix(),
             "bytes": path.stat().st_size, "sha256": digest(path)} for path in files]
    if len({row["path"].casefold() for row in rows}) != len(rows):
        raise RuntimeError("Case-colliding Rift evidence paths")
    return files, rows, total


def self_test() -> None:
    manifest, _ = read_manifest()
    if manifest["release"]["releaseId"] != RELEASE_ID or manifest["apk"]["sha256"] != APK_SHA:
        raise AssertionError("Rift input manifest not fixed")
    sample = {"id": RELEASE_ID, "tag_name": TAG, "draft": True,
              "assets": [{"id": ASSET_ID, "name": APK_NAME, "size": APK_BYTES,
                          "digest": "sha256:" + APK_SHA, "state": "uploaded"}]}
    verify_release(sample)
    try:
        verify_release({**sample, "draft": False})
    except RuntimeError:
        pass
    else:
        raise AssertionError("Published release accepted")
    print(json.dumps({"status": "RIFT_EVIDENCE_CONTRACT_SELF_TEST_PASSED",
                      "networkUsed": False, "releaseWritten": False}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    manifest, raw_manifest = read_manifest()
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != REPO
            or os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"
            or not os.environ.get("GH_TOKEN")):
        raise RuntimeError("Only original dedicated Rift QA run may publish evidence")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    head_sha = os.environ.get("GITHUB_SHA", "")
    if (not re.fullmatch(r"[1-9][0-9]{0,19}", run_id)
            or not re.fullmatch(r"[0-9a-f]{40}", head_sha)):
        raise RuntimeError("Invalid Rift one-shot run identity")
    raw_temp = os.environ.get("RUNNER_TEMP", "")
    raw_workspace = os.environ.get("GITHUB_WORKSPACE", "")
    if not os.path.isabs(raw_temp) or not os.path.isabs(raw_workspace):
        raise RuntimeError("Absolute runner temp and workspace required")
    temp = Path(raw_temp)
    workspace = Path(raw_workspace)
    if temp.is_symlink() or workspace.is_symlink():
        raise RuntimeError("Runner roots may not be linked")
    temp = temp.resolve()
    workspace = workspace.resolve()
    output = owned_output(workspace, run_id, head_sha)
    name = f"{OWNER}-{run_id}-attempt1.zip"
    archive = temp / name
    if archive.exists() or archive.is_symlink():
        raise RuntimeError("Unique Rift evidence archive already exists; no overwrite or retry")
    for reserved in ("input-manifest.json", "run-identity.json", "evidence-index.json"):
        if (output / reserved).exists() or (output / reserved).is_symlink():
            raise RuntimeError("Rift evidence packaging already attempted; no overwrite")
    if not (output / "native-observation.json").is_file():
        marker = output / "probe-not-started.json"
        if marker.exists() or marker.is_symlink():
            raise RuntimeError("Rift probe absence marker already exists")
        marker.write_text(json.dumps({"status": "NO_NATIVE_PROBE_OUTPUT",
                                      "runId": run_id}, indent=2) + "\n", encoding="utf-8")
    (output / "input-manifest.json").write_bytes(raw_manifest)
    identity = {"runId": run_id, "attempt": "1", "headSha": head_sha,
                "apkSha256": APK_SHA,
                "isolatedUnityProjectCommit": manifest["source"]["isolatedUnityProjectCommit"],
                "buildScriptPatchSha256": manifest["source"]["buildScriptPatchSha256"],
                "riftHudSha256": manifest["source"]["riftHudSha256"],
                "riftGameSha256": manifest["source"]["riftGameSha256"],
                "resourcesMetaSha256": manifest["source"]["resourcesMetaSha256"],
                "riftUrpLitMaterialSha256": manifest["source"]["riftUrpLitMaterialSha256"],
                "riftUrpLitMaterialMetaSha256": manifest["source"]["riftUrpLitMaterialMetaSha256"],
                "linkXmlSha256": manifest["source"]["linkXmlSha256"],
                "linkXmlMetaSha256": manifest["source"]["linkXmlMetaSha256"],
                "atUtc": datetime.now(timezone.utc).isoformat(),
                "storeWrites": 0, "firebaseWrites": 0,
                "physicalDeviceTested": False, "storeReady": False}
    (output / "run-identity.json").write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    files, rows, total = indexed_files(output)
    index = output / "evidence-index.json"
    index.write_text(json.dumps({"files": rows, "totalBytes": total}, indent=2) + "\n", encoding="utf-8")
    files.append(index)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zip_out:
        for path in files:
            zip_out.write(path, path.relative_to(output).as_posix())
    archive_sha = digest(archive)
    release = gh_release()
    verify_release(release)
    if any(asset.get("name") == name for asset in release.get("assets", [])):
        raise RuntimeError("Unique Rift evidence asset already exists; no overwrite")
    upload = subprocess.run(["gh", "release", "upload", TAG, str(archive), "--repo", REPO],
                            capture_output=True, timeout=180)
    if upload.returncode != 0:
        raise RuntimeError("Rift evidence upload outcome uncertain; inspect draft before any retry")
    readback = gh_release()
    verify_release(readback)
    matches = [asset for asset in readback.get("assets", []) if asset.get("name") == name]
    if (len(matches) != 1 or matches[0].get("state") != "uploaded"
            or matches[0].get("size") != archive.stat().st_size
            or matches[0].get("digest") != "sha256:" + archive_sha):
        raise RuntimeError("Rift evidence upload readback uncertain; no retry")
    print(json.dumps({"status": "ONE_SHOT_RIFT_DRAFT_EVIDENCE_UPLOAD_VERIFIED",
                      "releaseId": RELEASE_ID, "assetId": matches[0]["id"],
                      "name": name, "bytes": archive.stat().st_size,
                      "sha256": archive_sha, "storeWrites": 0,
                      "firebaseWrites": 0}))


if __name__ == "__main__":
    main()
