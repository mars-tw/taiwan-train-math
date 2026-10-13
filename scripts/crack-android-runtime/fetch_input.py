"""One fixed Crack code2 APK, official authenticated GitHub GETs only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

REPO = "mars-tw/taiwan-train-math"
BRANCH = "refs/heads/codex/crack2-kvm-qa-20261013-r11"
RELEASE_ID = 410075088
TAG = "crack-native-runtime-20261012-build2"
ASSET_ID = 632396712
NAME = "crackveil-vanguard-1.0.0-build2.apk"
SIZE = 68463980
SHA = "0b3a4aec652ce8cbb5110688670df3ef7d60bce28d13668c3fa6f22d5e54a8d2"


def gh_get(resource, binary=False):
    argv = ["gh", "api", resource]
    if binary:
        argv += ["-H", "Accept: application/octet-stream"]
    result = subprocess.run(argv, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError("Fixed official input GET failed; authenticated provider output withheld")
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_REPOSITORY") != REPO or os.environ.get("GITHUB_REF") != BRANCH:
        raise RuntimeError("Crack QA branch only")
    root = Path(os.environ["RUNNER_TEMP"]).resolve()
    dest = Path(args.directory).resolve()
    if not dest.is_relative_to(root) or dest == root or dest.exists():
        raise RuntimeError("Fresh own runner input directory required")
    release = json.loads(gh_get(f"repos/{REPO}/releases/{RELEASE_ID}"))
    if (release.get("id") != RELEASE_ID or release.get("draft") is not True
            or release.get("tag_name") != TAG):
        raise RuntimeError("Fixed private draft identity mismatch")
    matches = [a for a in release.get("assets", []) if a.get("id") == ASSET_ID]
    if len(matches) != 1:
        raise RuntimeError("Fixed APK asset missing or ambiguous")
    asset = matches[0]
    if asset.get("name") != NAME or asset.get("size") != SIZE or asset.get("digest") != "sha256:" + SHA:
        raise RuntimeError("Fixed APK metadata differs")
    raw = gh_get(f"repos/{REPO}/releases/assets/{ASSET_ID}", binary=True)
    if len(raw) != SIZE or hashlib.sha256(raw).hexdigest() != SHA:
        raise RuntimeError("Frozen APK byte/hash mismatch")
    dest.mkdir(mode=0o700)
    (dest / NAME).write_bytes(raw)
    provenance = {"schemaVersion": 1, "projectId": "crackveil-vanguard",
        "repository": REPO, "releaseId": RELEASE_ID, "tag": TAG, "draft": True,
        "assetId": ASSET_ID, "assetApiUrl": f"https://api.github.com/repos/{REPO}/releases/assets/{ASSET_ID}",
        "apkName": NAME, "apkBytes": SIZE, "apkSha256": SHA,
        "certificateSha256": "7166f66b5a182f2330c380fd57bd6f2821247db519b59ab9abe5aa554968c797",
        "packageName": "tw.mars.crackveilvanguard", "versionName": "1.0.0", "versionCode": 2,
        "sourceCommit": "713f0dd0f33eed63c8268bdebd5adf76bf603aff",
        "sourceCommitMeaning": "Original HEAD pointer only; actual raw634 snapshot is separately hash-bound.",
        "rawSourceManifestSha256": "975871052ae1a04944b009957b09afc0db74ced44bcbcfbd66b48bb3a01cdb0a",
        "sourceIOSPckSha256": "a6676ef12cf8badb262ebdd475db0e6eafb2c74369666f7c8ca56d4d5c1e17d0",
        "sourcePckPinIsContextNotAndroidPckComparison": True,
        "apkExecutedInFetchJob": False, "storeWrites": 0, "signerSecretsUsed": False}
    (dest / "fetch-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print("Fixed Crack2 private APK downloaded and hashed; no app or signer executed.")


if __name__ == "__main__":
    main()
