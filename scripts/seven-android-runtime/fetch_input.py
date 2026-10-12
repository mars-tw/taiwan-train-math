"""One fixed Seven code7 APK, official authenticated GitHub GETs only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

REPO = "mars-tw/taiwan-train-math"
BRANCH = "refs/heads/codex/ashes-simulator-recording"
RELEASE_ID = 410150466  # Root must bind actual verified private draft release7 ID.
TAG = "seven-native-runtime-20261012-build7"
ASSET_ID = 632622782  # Root must bind actual verified signed APK7 asset ID.
NAME = "seven-district-reckoning-1.0.0-build7.apk"
SIZE = 42696838  # Actual signed APK7 bytes, not unsigned7 bytes.
SHA = "b3dfeabf53a383f16b60f65814edec71759c22ff4fae6c62287ede6235446e93"  # Actual signed APK7 SHA-256, never the unsigned APK hash.


def fixed_input_pins():
    import re
    if (type(RELEASE_ID) is not int or RELEASE_ID <= 0 or type(ASSET_ID) is not int or ASSET_ID <= 0
            or type(SIZE) is not int or SIZE <= 0 or not isinstance(SHA, str)
            or not re.fullmatch(r"[0-9a-f]{64}", SHA)):
        raise RuntimeError("Seven7 signed APK/private draft pins are pending Root verification; stop before GET or runtime")
    if RELEASE_ID == 410057459 or ASSET_ID == 632341589 or SHA in {
            "f72044f7b2c1a1fb44b099128b8e7446fc3ba8531c8946b1dddd7e5f7482bee7",
            "61df33be7a5ee2ad2f3ca7e16cd45b91be014d3801c6dda96be83ebf4648fd6a"}:
        raise RuntimeError("Seven7 must use its exact signed identity, not frozen6 or unsigned7")
    return {"releaseId": RELEASE_ID, "assetId": ASSET_ID, "bytes": SIZE, "sha256": SHA,
            "name": NAME, "tag": TAG, "versionCode": 7}


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
    fixed_input_pins()
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
        "packageName": "tw.mars.sevendistrictreckoning", "versionName": "1.0.0", "versionCode": 7,
        "sourceOriginalCommitContext": "c08b28636ed9fc6c8cb746213513117072e7e0fc",
        "sourceOriginalInputsSha256": "5dacaa87cda4d2f1c21e94b0c5bd8e8a4cdff16b49a9f39e18ef342be88eeeba",
        "sourcePostOverridesInputsSha256": "e486a578116242aaa7a1fe7394ffe5aec1adb3c4dc2bb1ca852846f3a06436a9",
        "sourceOverridesManifestSha256": "f724e74de1e6c58b4cecc9de28bd6ee73c431664f80bc110bd61fcc125d86971",
        "sourceInputOverrides": 4,
        "apkExecutedInFetchJob": False, "storeWrites": 0, "signerSecretsUsed": False}
    (dest / "fetch-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print("Fixed Seven7 private APK downloaded and hashed; no app or signer executed.")


if __name__ == "__main__":
    main()
