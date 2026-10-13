"""Fetch only the pinned Seven build-10 draft asset for one KVM QA run."""
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
BRANCH = "refs/heads/codex/seven-build10-native-qa"
APK_SHA = "a052ec9e540c4bb0c507f1ff140794c124d40e9bc45b1b1081d139de8b02e22d"
CERT_SHA = "1dd3cc96a02e4555e8d91a42d749a019ee5c4781d4d7510947ae48c865e21110"
BASE_SHA = "a6b28e9be5f8cf1c2630097fe6e5b4a0af23c1c893b29efea58dc34c8b8311b9"
OPT_SHA = "e717397651c82fc4a3790414ebe06d1b1a2d040ae44b1c005ee5c83320a9a995"
SOURCE_BIND_SHA = "9da50aded85dade6aa46e0b854052bcfa529c41a98bb2e2bccd323b5fcce6ee2"
APK_NAME = "seven-district-reckoning-1.0.0-build10-test-signed.apk"
APK_BYTES = 90553263


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest():
    raw = MANIFEST.read_bytes()
    m = json.loads(raw)
    if (m.get("schemaVersion") != 1 or m.get("projectId") != "seven-district-reckoning"
            or m.get("repository") != REPO or m.get("branch") != BRANCH.removeprefix("refs/heads/")
            or m.get("appId") != "tw.mars.sevendistrictreckoning"
            or m.get("versionName") != "1.0.0" or m.get("versionCode") != 10
            or m.get("apk") != {"file": APK_NAME, "bytes": APK_BYTES, "sha256": APK_SHA, "certificateSha256": CERT_SHA}
            or m.get("source", {}).get("basePatchSha256") != BASE_SHA
            or m.get("source", {}).get("optimizationPatchSha256") != OPT_SHA
            or m.get("source", {}).get("sourceBindSha256") != SOURCE_BIND_SHA
            or m.get("runtime", {}).get("image") != "system-images;android-36;google_apis;x86_64"
            or m.get("runtime", {}).get("imageRevision") != 7
            or m.get("runtime", {}).get("bridge") != "libndk_translation.so"
            or m.get("runtime", {}).get("gpu") != "swangle"
            or m.get("release", {}).get("draft") is not True
            or not re.fullmatch(r"seven-build10-kvm-qa-20261013-a052ec9e-[a-f0-9]{12}", str(m.get("release", {}).get("tag", "")))):
        raise RuntimeError("Fixed build-10 input manifest differs")
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
    dest = temp / "seven-build10-input"
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
        "basePatchSha256": m["source"]["basePatchSha256"],
        "optimizationPatchSha256": OPT_SHA, "sourceBindSha256": SOURCE_BIND_SHA,
        "storeWrites": 0, "firebaseWrites": 0, "signerSecretsUsed": False}
    (dest / "fetch-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "EXACT_DRAFT_APK_FETCH_VERIFIED", "apkSha256": APK_SHA, "manifestSha256": provenance["manifestSha256"]}))


if __name__ == "__main__":
    main()
