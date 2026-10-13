"""Fetch only the pinned Seven build-11 draft asset for one KVM QA run."""
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
BRANCH = "refs/heads/codex/seven-build11-r12-native-qa"
APK_SHA = "690a46a0447c322f9c096f8d83fe108e354709a50fc26d0cb2b592923c951823"
CERT_SHA = "1dd3cc96a02e4555e8d91a42d749a019ee5c4781d4d7510947ae48c865e21110"
BASE_SHA = "e717397651c82fc4a3790414ebe06d1b1a2d040ae44b1c005ee5c83320a9a995"
OPT_SHA = "4fb0cca3b9f20915f09cc70935f1a2956eb8e3c5dc5b751d5ae04631989b0200"
SOURCE_BIND_SHA = "1015dce084c55afbd5f7cb301b3fd9b998e2056df62b3a05ac9fc4ba8c084037"
APK_NAME = "seven-district-reckoning-1.0.0-build11-test-signed.apk"
APK_BYTES = 90561618


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest():
    raw = MANIFEST.read_bytes()
    m = json.loads(raw)
    if (m.get("schemaVersion") != 1 or m.get("projectId") != "seven-district-reckoning"
            or m.get("repository") != REPO or m.get("branch") != BRANCH.removeprefix("refs/heads/")
            or m.get("appId") != "tw.mars.sevendistrictreckoning"
            or m.get("versionName") != "1.0.0" or m.get("versionCode") != 11
            or m.get("apk") != {"file": APK_NAME, "bytes": APK_BYTES, "sha256": APK_SHA, "certificateSha256": CERT_SHA}
            or m.get("source", {}).get("baseOptimizationPatchSha256") != BASE_SHA
            or m.get("source", {}).get("titleCtaPatchSha256") != OPT_SHA
            or m.get("source", {}).get("sourceBindSha256") != SOURCE_BIND_SHA
            or m.get("runtime", {}).get("image") != "system-images;android-36;google_apis;x86_64"
            or m.get("runtime", {}).get("imageRevision") != 7
            or m.get("runtime", {}).get("bridge") != "libndk_translation.so"
            or m.get("runtime", {}).get("gpu") != "swangle"
            or m.get("release", {}).get("draft") is not True
            or not re.fullmatch(r"seven-build11-r12-kvm-qa-20261013-690a46a0-[a-f0-9]{12}", str(m.get("release", {}).get("tag", "")))):
        raise RuntimeError("Fixed build-11 input manifest differs")
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
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REPOSITORY") != REPO or os.environ.get("GITHUB_REF") != BRANCH:
        raise RuntimeError("Fixed public QA branch only")
    release_id, asset_id = m["release"].get("releaseId"), m["release"].get("assetId")
    if (type(release_id) is not int or release_id <= 0 or type(asset_id) is not int or asset_id <= 0
            or m.get("status") != "READY_FIXED_DRAFT_RELEASE"):
        raise RuntimeError("Unique draft release/asset IDs are not pinned")
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    dest = temp / "seven-build11-r12-input"
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
        "baseOptimizationPatchSha256": m["source"]["baseOptimizationPatchSha256"],
        "titleCtaPatchSha256": OPT_SHA, "sourceBindSha256": SOURCE_BIND_SHA,
        "storeWrites": 0, "firebaseWrites": 0, "signerSecretsUsed": False}
    (dest / "fetch-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "EXACT_DRAFT_APK_FETCH_VERIFIED", "apkSha256": APK_SHA, "manifestSha256": provenance["manifestSha256"]}))


if __name__ == "__main__":
    main()
