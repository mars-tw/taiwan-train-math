"""One fixed Seven code8 APK, official authenticated GitHub GETs only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

REPO = "mars-tw/taiwan-train-math"
BRANCH = "refs/heads/codex/ashes-simulator-recording"
RELEASE_ID = 410168487  # Root actual signed8/private draft receipt, independently local byte-hashed.
TAG = "seven-native-runtime-20261012-build8"
ASSET_ID = 632677229  # Root actual signed8/private draft receipt, independently local byte-hashed.
NAME = "seven-district-reckoning-1.0.0-build8.apk"
SIZE = 42696838  # Root actual signed8/private draft receipt, independently local byte-hashed.
SHA = '0a714ff809587bcaa1ce56d3c0f448a399bd9c17203442eef724e7b02d83593b'  # Root actual signed8/private draft receipt, independently local byte-hashed.


def fixed_input_pins():
    import re
    if (type(RELEASE_ID) is not int or RELEASE_ID <= 0 or type(ASSET_ID) is not int or ASSET_ID <= 0
            or type(SIZE) is not int or SIZE <= 0 or not isinstance(SHA, str)
            or not re.fullmatch(r"[0-9a-f]{64}", SHA)):
        raise RuntimeError("Seven8 signed APK/private draft pins are pending Root verification; stop before GET or runtime")
    if RELEASE_ID in {410057459, 410150466} or ASSET_ID in {632341589, 632622782} or SHA in {
            "f72044f7b2c1a1fb44b099128b8e7446fc3ba8531c8946b1dddd7e5f7482bee7",
            "b3dfeabf53a383f16b60f65814edec71759c22ff4fae6c62287ede6235446e93",
            "404a6900fac2c899e4034a46397350dc5bb99b4fbcc2a92be240f10045d0f125",
            "61df33be7a5ee2ad2f3ca7e16cd45b91be014d3801c6dda96be83ebf4648fd6a"}:
        raise RuntimeError("Seven8 must use its exact signed identity, not previous frozen6/signed7 or unsigned8")
    return {"releaseId": RELEASE_ID, "assetId": ASSET_ID, "bytes": SIZE, "sha256": SHA,
            "name": NAME, "tag": TAG, "versionCode": 8}


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
        "packageName": "tw.mars.sevendistrictreckoning", "versionName": "1.0.0", "versionCode": 8,
        "sourceOriginalCommitContext": "c08b28636ed9fc6c8cb746213513117072e7e0fc",
        "sourceFrozen6OriginalInputsContextSha256": "5dacaa87cda4d2f1c21e94b0c5bd8e8a4cdff16b49a9f39e18ef342be88eeeba",
        "sourcePrevious7InputsSha256": "e486a578116242aaa7a1fe7394ffe5aec1adb3c4dc2bb1ca852846f3a06436a9",
        "sourcePostOverridesInputsSha256": "c4fd6196614ade90eb9b589788da4316acd6a4cbdbd71c68cb50d25408d96b5f",
        "sourceOverridesManifestSha256": "695d05a8e9392b39415778968317a8385b3be96190342b34c11867536b24d335",
        "sourceInputOverrides": 3,
        "apkExecutedInFetchJob": False, "storeWrites": 0, "signerSecretsUsed": False}
    (dest / "fetch-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print("Fixed Seven8 private APK downloaded and hashed; no app or signer executed.")


if __name__ == "__main__":
    main()
