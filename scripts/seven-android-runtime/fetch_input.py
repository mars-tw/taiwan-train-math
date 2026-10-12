"""One fixed Seven code6 APK, official authenticated GitHub GETs only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

REPO = "mars-tw/taiwan-train-math"
BRANCH = "refs/heads/codex/ashes-simulator-recording"
RELEASE_ID = 410057459
TAG = "seven-native-runtime-20261012-build6"
ASSET_ID = 632341589
NAME = "seven-district-reckoning-1.0.0-build6.apk"
SIZE = 42696838
SHA = "f72044f7b2c1a1fb44b099128b8e7446fc3ba8531c8946b1dddd7e5f7482bee7"


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
        raise RuntimeError("Seven QA branch only")
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
    provenance = {"schemaVersion": 1, "projectId": "seven-district-reckoning",
        "repository": REPO, "releaseId": RELEASE_ID, "tag": TAG, "draft": True,
        "assetId": ASSET_ID, "assetApiUrl": f"https://api.github.com/repos/{REPO}/releases/assets/{ASSET_ID}",
        "apkName": NAME, "apkBytes": SIZE, "apkSha256": SHA,
        "certificateSha256": "1dd3cc96a02e4555e8d91a42d749a019ee5c4781d4d7510947ae48c865e21110",
        "packageName": "tw.mars.sevendistrictreckoning", "versionName": "1.0.0", "versionCode": 6,
        "sourceCommit": "c08b28636ed9fc6c8cb746213513117072e7e0fc",
        "sourceIOSPckSha256": "16f788b46069c3b2c135009015d3ae90b7252e437e471c981932af1942fe1d07",
        "sourcePckPinIsContextNotAndroidPckComparison": True,
        "apkExecutedInFetchJob": False, "storeWrites": 0, "signerSecretsUsed": False}
    (dest / "fetch-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print("Fixed Seven6 private APK downloaded and hashed; no app or signer executed.")


if __name__ == "__main__":
    main()
