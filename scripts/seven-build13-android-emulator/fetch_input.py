"""Fetch only the pinned Seven build-13 draft asset for one manual KVM QA run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "manifest.json"
REPO = "mars-tw/taiwan-train-math"
BRANCH = "refs/heads/main"
APK_SHA = "dc5acee20ce5d4a63d63feb29d2f1bd66daa27f8a58a21cc4988f2b3c75fea14"
CERT_SHA = "1dd3cc96a02e4555e8d91a42d749a019ee5c4781d4d7510947ae48c865e21110"
SOURCE_COMMIT = "b9377588c91b95bba81e98c343e51886f3d38b01"
SOURCE_FINGERPRINT = "98806f1459476c3e21e5ecc02fdfc9aa38dac785c3a911aa7f46661a7d7d4098"
VALIDATION_SHA = "e86cd400dfd3a385d30c78d3f789529aaa2ef9cb586408502f468bdd3c214e06"
APK_NAME = "seven-build13-signed.apk"
APK_BYTES = 42730264


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest():
    raw = MANIFEST.read_bytes()
    m = json.loads(raw)
    if (m.get("schemaVersion") != 1 or m.get("projectId") != "seven-district-reckoning"
            or m.get("repository") != REPO or m.get("branch") != BRANCH.removeprefix("refs/heads/")
            or m.get("appId") != "tw.mars.sevendistrictreckoning"
            or m.get("versionName") != "1.0.0" or m.get("versionCode") != 13
            or m.get("apk") != {"file": APK_NAME, "bytes": APK_BYTES, "sha256": APK_SHA, "certificateSha256": CERT_SHA}
            or m.get("source", {}).get("sourceCommit") != SOURCE_COMMIT
            or m.get("source", {}).get("sourceFingerprint") != SOURCE_FINGERPRINT
            or m.get("source", {}).get("buildValidationSha256") != VALIDATION_SHA
            or m.get("runtime", {}).get("image") != "system-images;android-36;google_apis;x86_64"
            or m.get("runtime", {}).get("imageRevision") != 7
            or m.get("runtime", {}).get("bridge") != "libndk_translation.so"
            or m.get("runtime", {}).get("gpu") != "swangle"
            or m.get("release", {}).get("draft") is not True
            or m.get("release", {}).get("tag") != "seven-build13-android-emulator-qa-20261014-dc5acee2"
            or m.get("release", {}).get("releaseId") != 411970894
            or m.get("release", {}).get("assetId") != 637853632):
        raise RuntimeError("Fixed build-13 input manifest differs")
    return m, raw


def gh_get(resource, binary=False):
    command = ["gh", "api", resource]
    if binary:
        command += ["-H", "Accept: application/octet-stream"]
    result = subprocess.run(command, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError("GitHub draft GET failed; provider output withheld")
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--local-apk", type=Path)
    args = parser.parse_args()
    m, raw = manifest()
    if args.self_test:
        if args.local_apk is None or not args.local_apk.is_file():
            raise RuntimeError("Self-test requires existing local exact APK")
        data = args.local_apk.read_bytes()
        if len(data) != APK_BYTES or sha(data) != APK_SHA:
            raise RuntimeError("Local APK byte pin mismatch")
        print(json.dumps({"status": "LOCAL_MANIFEST_APK_PIN_VERIFIED", "apkSha256": APK_SHA, "manifestSha256": sha(raw)}))
        return
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.environ.get("GITHUB_REPOSITORY") != REPO
            or os.environ.get("GITHUB_REF") != BRANCH
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"):
        raise RuntimeError("Original manual GitHub Actions main attempt only")
    release_id, asset_id = m["release"].get("releaseId"), m["release"].get("assetId")
    if (type(release_id) is not int or release_id <= 0 or type(asset_id) is not int or asset_id <= 0
            or m.get("status") != "READY_FIXED_DRAFT_RELEASE"):
        raise RuntimeError("Unique draft release/asset IDs are not pinned")
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    dest = temp / "seven-build13-android-emulator-input"
    if dest.exists():
        raise RuntimeError("Owned fetch directory already exists; do not overwrite")
    release = json.loads(gh_get(f"repos/{REPO}/releases/{release_id}"))
    if (release.get("id") != release_id or release.get("draft") is not True
            or release.get("tag_name") != m["release"]["tag"]):
        raise RuntimeError("Draft release identity mismatch")
    matches = [a for a in release.get("assets", []) if a.get("id") == asset_id]
    if len(matches) != 1:
        raise RuntimeError("Pinned APK asset missing or ambiguous")
    asset = matches[0]
    if (asset.get("name") != APK_NAME or asset.get("size") != APK_BYTES
            or asset.get("digest") != "sha256:" + APK_SHA or asset.get("state") != "uploaded"):
        raise RuntimeError("Pinned APK asset metadata differs")
    data = gh_get(f"repos/{REPO}/releases/assets/{asset_id}", binary=True)
    if len(data) != APK_BYTES or sha(data) != APK_SHA:
        raise RuntimeError("Downloaded signed APK byte/hash mismatch")
    dest.mkdir(mode=0o700)
    (dest / APK_NAME).write_bytes(data)
    (dest / "manifest.json").write_bytes(raw)
    provenance = {"schemaVersion": 1, "projectId": m["projectId"], "repository": REPO,
        "branch": m["branch"], "releaseId": release_id, "assetId": asset_id,
        "releaseTag": m["release"]["tag"], "releaseDraft": True,
        "appId": m["appId"], "versionName": m["versionName"], "versionCode": m["versionCode"],
        "apkFile": APK_NAME, "apkBytes": APK_BYTES, "apkSha256": APK_SHA,
        "certificateSha256": CERT_SHA, "manifestSha256": sha(raw),
        "sourceCommit": m["source"]["sourceCommit"],
        "sourceFingerprint": SOURCE_FINGERPRINT, "buildValidationSha256": VALIDATION_SHA,
        "storeWrites": 0, "firebaseWrites": 0, "signerSecretsUsed": False}
    (dest / "fetch-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "EXACT_DRAFT_APK_FETCH_VERIFIED", "apkSha256": APK_SHA, "manifestSha256": provenance["manifestSha256"]}))


if __name__ == "__main__":
    main()
