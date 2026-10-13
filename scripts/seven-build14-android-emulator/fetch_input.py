"""Fetch only the pinned Seven build-14 draft asset for one manual KVM QA run."""
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
APK_SHA = "bd72d2697dc91b995ba55f59d82d4b5c5764e2401f6ec48012ec910257de73e7"
CERT_SHA = "1dd3cc96a02e4555e8d91a42d749a019ee5c4781d4d7510947ae48c865e21110"
SIGNING_RECEIPT_SHA = "e77d06696aa2452650f3cd91ebcc31613231c9053d3f1cf43060d7ae0f0a6e3e"
SIGNING_RECEIPT_ASSET_ID = 638148545
APPROVAL_MANIFEST_SHA = "70fe49b8212ac707484c3f56a7b6370e96fa8ec4fb8f6e959ebb748d16c9b17e"
APPROVAL_MANIFEST_ASSET_ID = 638148547
UNSIGNED_BUNDLE_SHA = "8d54def5d07c8b9818a8ac8e2401f8e8d72f36c8169bc9b0e52004dd9d3df62b"
SOURCE_COMMIT = "a5cc913f566189d13ecf39b4229848fec8a43df1"
SOURCE_FINGERPRINT = "bd3709e4363ac957b9316863a8896eed3739611531fa86c487ac24050f061d80"
VALIDATION_SHA = "cba46710fe015c5d11a4fe291d4cc2998666152c3093ebc360f4e8807f3cc67d"
APK_NAME = "seven-build14-signed.apk"
APK_BYTES = 42734360


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifest():
    raw = MANIFEST.read_bytes()
    m = json.loads(raw)
    if (m.get("schemaVersion") != 1 or m.get("projectId") != "seven-district-reckoning"
            or m.get("repository") != REPO or m.get("branch") != BRANCH.removeprefix("refs/heads/")
            or m.get("appId") != "tw.mars.sevendistrictreckoning"
            or m.get("versionName") != "1.0.0" or m.get("versionCode") != 14
            or m.get("apk") != {"file": APK_NAME, "bytes": APK_BYTES, "sha256": APK_SHA, "certificateSha256": CERT_SHA}
            or m.get("signingReceipt") != {"file": "verification.json", "bytes": 2125,
                                           "sha256": SIGNING_RECEIPT_SHA, "assetId": SIGNING_RECEIPT_ASSET_ID}
            or m.get("approvalManifest") != {"file": "emulator-input-manifest.json", "bytes": 1204,
                                            "sha256": APPROVAL_MANIFEST_SHA, "assetId": APPROVAL_MANIFEST_ASSET_ID}
            or m.get("source", {}).get("sourceCommit") != SOURCE_COMMIT
            or m.get("source", {}).get("sourceFingerprint") != SOURCE_FINGERPRINT
            or m.get("source", {}).get("buildValidationSha256") != VALIDATION_SHA
            or m.get("runtime", {}).get("image") != "system-images;android-36;google_apis;x86_64"
            or m.get("runtime", {}).get("imageRevision") != 7
            or m.get("runtime", {}).get("bridge") != "libndk_translation.so"
            or m.get("runtime", {}).get("gpu") != "swangle"
            or m.get("release", {}).get("draft") is not True
            or m.get("release", {}).get("tag") != "seven-build14-android-emulator-qa-20261014-bd72d269"
            or m.get("release", {}).get("releaseId") != 412073733
            or m.get("release", {}).get("assetId") != 638148548):
        raise RuntimeError("Fixed build-14 input manifest differs")
    return m, raw


def gh_get(resource, binary=False):
    command = ["gh", "api", resource]
    if binary:
        command += ["-H", "Accept: application/octet-stream"]
    result = subprocess.run(command, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError("GitHub draft GET failed; provider output withheld")
    return result.stdout


def verify_signing_receipt(receipt):
    if (receipt.get("status"), receipt.get("sourceCommit"),
            receipt.get("signed", {}).get("apk", {}).get("file"),
            receipt.get("signed", {}).get("apk", {}).get("bytes"),
            receipt.get("signed", {}).get("apk", {}).get("sha256"),
            receipt.get("certificateSha256"), receipt.get("payloadEquivalent"),
            receipt.get("unsignedBundleSha256"), receipt.get("storeUploadPerformed")) != (
                "VERIFIED_SIGNED_ANDROID_BUILD14_LOCAL_ONLY", SOURCE_COMMIT,
                APK_NAME, APK_BYTES, APK_SHA, CERT_SHA, True, UNSIGNED_BUNDLE_SHA, False):
        raise RuntimeError("Downloaded signed source receipt claims differ")


def verify_approval_manifest(approval):
    if (approval.get("status"), approval.get("appId"), approval.get("versionCode"),
            approval.get("source", {}).get("sourceCommit"),
            approval.get("source", {}).get("sourceFingerprint"),
            approval.get("source", {}).get("buildValidationSha256"),
            approval.get("source", {}).get("unsignedBundleSha256"),
            approval.get("apk", {}).get("file"), approval.get("apk", {}).get("bytes"),
            approval.get("apk", {}).get("sha256"),
            approval.get("apk", {}).get("certificateSha256"),
            approval.get("signingReceipt", {}).get("sha256"),
            approval.get("policy", {}).get("storeWrites")) != (
                "READY_SIGNED_BUILD14_EMULATOR_INPUT", "tw.mars.sevendistrictreckoning", 14,
                SOURCE_COMMIT, SOURCE_FINGERPRINT, VALIDATION_SHA, UNSIGNED_BUNDLE_SHA,
                APK_NAME, APK_BYTES, APK_SHA, CERT_SHA, SIGNING_RECEIPT_SHA, 0):
        raise RuntimeError("Approved source manifest does not bind signed APK and build proof")


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
    dest = temp / "seven-build14-android-emulator-input"
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
    receipt_assets = [a for a in release.get("assets", []) if a.get("id") == SIGNING_RECEIPT_ASSET_ID]
    if len(receipt_assets) != 1 or any(receipt_assets[0].get(key) != value for key, value in {
            "name": "verification.json", "size": 2125,
            "digest": "sha256:" + SIGNING_RECEIPT_SHA, "state": "uploaded"}.items()):
        raise RuntimeError("Pinned signing receipt asset differs")
    receipt_bytes = gh_get(f"repos/{REPO}/releases/assets/{SIGNING_RECEIPT_ASSET_ID}", binary=True)
    if len(receipt_bytes) != 2125 or sha(receipt_bytes) != SIGNING_RECEIPT_SHA:
        raise RuntimeError("Downloaded signed source receipt byte/hash mismatch")
    receipt = json.loads(receipt_bytes)
    verify_signing_receipt(receipt)
    approval_assets = [a for a in release.get("assets", []) if a.get("id") == APPROVAL_MANIFEST_ASSET_ID]
    if len(approval_assets) != 1 or any(approval_assets[0].get(key) != value for key, value in {
            "name": "emulator-input-manifest.json", "size": 1204,
            "digest": "sha256:" + APPROVAL_MANIFEST_SHA, "state": "uploaded"}.items()):
        raise RuntimeError("Pinned approved source manifest asset differs")
    approval_bytes = gh_get(f"repos/{REPO}/releases/assets/{APPROVAL_MANIFEST_ASSET_ID}", binary=True)
    if len(approval_bytes) != 1204 or sha(approval_bytes) != APPROVAL_MANIFEST_SHA:
        raise RuntimeError("Downloaded approved source manifest byte/hash mismatch")
    approval = json.loads(approval_bytes)
    verify_approval_manifest(approval)
    dest.mkdir(mode=0o700)
    (dest / APK_NAME).write_bytes(data)
    (dest / "manifest.json").write_bytes(raw)
    (dest / "verification.json").write_bytes(receipt_bytes)
    (dest / "emulator-input-manifest.json").write_bytes(approval_bytes)
    provenance = {"schemaVersion": 1, "projectId": m["projectId"], "repository": REPO,
        "branch": m["branch"], "releaseId": release_id, "assetId": asset_id,
        "releaseTag": m["release"]["tag"], "releaseDraft": True,
        "appId": m["appId"], "versionName": m["versionName"], "versionCode": m["versionCode"],
        "apkFile": APK_NAME, "apkBytes": APK_BYTES, "apkSha256": APK_SHA,
        "certificateSha256": CERT_SHA, "manifestSha256": sha(raw),
        "signingReceiptSha256": SIGNING_RECEIPT_SHA,
        "signingReceiptAssetId": SIGNING_RECEIPT_ASSET_ID,
        "approvalManifestSha256": APPROVAL_MANIFEST_SHA,
        "approvalManifestAssetId": APPROVAL_MANIFEST_ASSET_ID,
        "unsignedBundleSha256": UNSIGNED_BUNDLE_SHA,
        "sourceCommit": m["source"]["sourceCommit"],
        "sourceFingerprint": SOURCE_FINGERPRINT, "buildValidationSha256": VALIDATION_SHA,
        "storeWrites": 0, "firebaseWrites": 0, "signerSecretsUsed": False}
    (dest / "fetch-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "EXACT_DRAFT_APK_FETCH_VERIFIED", "apkSha256": APK_SHA, "manifestSha256": provenance["manifestSha256"]}))


if __name__ == "__main__":
    main()
