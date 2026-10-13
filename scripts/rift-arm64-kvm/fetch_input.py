"""Read one byte-pinned Rift development APK from its existing draft release."""

from __future__ import annotations

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
BRANCH = "codex/rift-arm64-kvm-r5-20261013-fastcombat"
REF = "refs/heads/" + BRANCH
TAG = "rift-android-dev-kvm-r3-20261013-aa8cb0bb-f4d48a85959e"
RELEASE_ID = 411337130
ASSET_ID = 636077860
APK_NAME = "RiftForge-dev-primitive-fix.apk"
APK_BYTES = 57_152_389
APK_SHA = "aa8cb0bbd1c0e236c415768ba0baafe646ad7db1e439f5ad4c8c09a38f80af28"
CERT_SHA = "11e100f23b70476c3a1b02054e85c9c9681609e5604fada346dd8f3fe3df4c40"
SOURCE_COMMIT = "d75c4ee24cfa4807bb833735a4b2a98f0e0f119c"
BUILD_SCRIPT_PATCH_SHA = "768b7366ceef9724c1b346a2bddd163e0ac544c4201b1783187718c67b83884a"
RIFT_HUD_SHA = "ff61c07cc8b39aae023368ad2d00176e0366cc83aea1a7a66b27a5702fa4ca18"
RIFT_GAME_SHA = "ad3d436c0c83ddb19c5fcae8b952602c5b2fa90f70fb1aefde674e63e541f684"
RESOURCES_META_SHA = "d79c6e564ff741b3406c2e31e61f1453b0e5dcc967a7511fbaad9a15d295c4c3"
RIFT_URP_LIT_SHA = "1e4e663de0cbc96dbb88d7180510c3ed358355dbeed8181fe778c2ead835c325"
RIFT_URP_LIT_META_SHA = "91bae78f2f3ff01e6624054f7b27856ab780e05ae55209ea03dec480936ff9ed"
LINK_XML_SHA = "0dc3e5e75226c9d2f2b0ca0088c616515225fd351154c42c2bfe5e69b5640c70"
LINK_XML_META_SHA = "56a95644af5a38c180f0186e271d967655636fc3a4bdda872e611a0f1fe121d0"
SYSTEM_IMAGE = "system-images;android-36;google_apis;x86_64"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_manifest() -> tuple[dict, bytes]:
    if MANIFEST.is_symlink() or not MANIFEST.is_file() or MANIFEST.stat().st_size > 16_384:
        raise RuntimeError("Pinned manifest absent, linked or oversized")
    raw = MANIFEST.read_bytes()
    manifest = json.loads(raw)
    exact = {
        "schemaVersion": 1, "status": "READY_FIXED_DRAFT_RELEASE",
        "projectId": "rift-forge-3d", "repository": REPO, "branch": BRANCH,
        "appId": "tw.mars.riftforge3d", "versionName": "1.0.0", "versionCode": 1,
    }
    if (not isinstance(manifest, dict) or type(manifest.get("versionCode")) is not int
            or any(manifest.get(k) != v for k, v in exact.items())):
        raise RuntimeError("Fixed Rift manifest identity differs")
    expected_apk = {"file": APK_NAME, "bytes": APK_BYTES, "sha256": APK_SHA,
                    "certificateSha256": CERT_SHA, "signing": "Android Debug"}
    expected_source = {"isolatedUnityProjectCommit": SOURCE_COMMIT,
                       "buildScriptPatchSha256": BUILD_SCRIPT_PATCH_SHA,
                       "riftHudSha256": RIFT_HUD_SHA,
                       "riftGameSha256": RIFT_GAME_SHA,
                       "resourcesMetaSha256": RESOURCES_META_SHA,
                       "riftUrpLitMaterialSha256": RIFT_URP_LIT_SHA,
                       "riftUrpLitMaterialMetaSha256": RIFT_URP_LIT_META_SHA,
                       "linkXmlSha256": LINK_XML_SHA,
                       "linkXmlMetaSha256": LINK_XML_META_SHA}
    expected_release = {"tag": TAG, "draft": True,
                        "releaseId": RELEASE_ID, "assetId": ASSET_ID}
    expected_runtime = {"apiLevel": 36, "image": SYSTEM_IMAGE,
                        "imageRevision": 7, "abi": "x86_64,arm64-v8a",
                        "bridge": "libndk_translation.so", "gpu": "swangle",
                        "emulatorVersion": "37.2.12", "buildToolsVersion": "36.1.0"}
    if (manifest.get("apk") != expected_apk or manifest.get("source") != expected_source
            or manifest.get("release") != expected_release
            or manifest.get("runtime") != expected_runtime):
        raise RuntimeError("Fixed Rift APK/source/draft/runtime pins differ")
    policy = manifest.get("policy", {})
    if (not isinstance(policy, dict) or policy.get("dedicatedBranchOnly") is not True
            or type(policy.get("oneShotRunAttempt")) is not int
            or policy.get("oneShotRunAttempt") != 1 or policy.get("runner") != "ubuntu-24.04"
            or policy.get("licensedSdkFromRunner") is not True
            or policy.get("sdkmanagerLicenseAcceptance") is not False
            or policy.get("storeWrites") != 0 or policy.get("firebaseWrites") != 0
            or policy.get("physicalDeviceClaim") is not False
            or policy.get("storeReadyClaim") is not False):
        raise RuntimeError("Fixed Rift QA policy differs")
    return manifest, raw


def gh_get(resource: str, *, binary: bool = False) -> bytes:
    command = ["gh", "api", resource]
    if binary:
        command += ["-H", "Accept: application/octet-stream"]
    result = subprocess.run(command, capture_output=True, timeout=240)
    if result.returncode != 0:
        raise RuntimeError("Exact draft GET failed; provider output withheld")
    return result.stdout


def verify_local_apk(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size != APK_BYTES:
        raise RuntimeError("Local Rift APK absent, linked or byte count differs")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != APK_SHA:
        raise RuntimeError("Local Rift APK SHA-256 differs")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--local-apk", type=Path)
    args = parser.parse_args()
    manifest, raw = read_manifest()
    if args.self_test:
        if args.local_apk is not None:
            verify_local_apk(args.local_apk)
        print(json.dumps({"status": "RIFT_INPUT_CONTRACT_VERIFIED",
                          "localApkVerified": args.local_apk is not None,
                          "apkSha256": APK_SHA, "manifestSha256": sha(raw)}))
        return
    if args.local_apk is not None:
        raise RuntimeError("--local-apk is valid only with --self-test")
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != REPO
            or os.environ.get("GITHUB_REF") != REF
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"
            or not os.environ.get("GH_TOKEN")):
        raise RuntimeError("One original run on the dedicated Rift QA branch only")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run_id):
        raise RuntimeError("Invalid owned GitHub run id")
    raw_temp = os.environ.get("RUNNER_TEMP", "")
    if not os.path.isabs(raw_temp):
        raise RuntimeError("Absolute runner temp required")
    temp = Path(raw_temp)
    if temp.is_symlink():
        raise RuntimeError("Runner temp may not be linked")
    dest = temp.resolve() / "rift-arm64-kvm-r5-input"
    if dest.exists() or dest.is_symlink():
        raise RuntimeError("Owned Rift input already exists; no overwrite or retry")
    release = json.loads(gh_get(f"repos/{REPO}/releases/{RELEASE_ID}"))
    if (release.get("id") != RELEASE_ID or release.get("draft") is not True
            or release.get("tag_name") != TAG):
        raise RuntimeError("Exact private draft identity differs")
    matches = [asset for asset in release.get("assets", []) if asset.get("id") == ASSET_ID]
    if len(matches) != 1:
        raise RuntimeError("Pinned Rift APK asset missing or ambiguous")
    asset = matches[0]
    if (asset.get("name") != APK_NAME or asset.get("size") != APK_BYTES
            or asset.get("digest") != "sha256:" + APK_SHA
            or asset.get("state") != "uploaded"):
        raise RuntimeError("Pinned Rift APK asset metadata differs")
    data = gh_get(f"repos/{REPO}/releases/assets/{ASSET_ID}", binary=True)
    if len(data) != APK_BYTES or sha(data) != APK_SHA:
        raise RuntimeError("Downloaded Rift APK bytes/hash differ; no install")
    dest.mkdir(mode=0o700)
    with (dest / APK_NAME).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    verify_local_apk(dest / APK_NAME)
    (dest / "manifest.json").write_bytes(raw)
    provenance = {
        "schemaVersion": 1, "projectId": manifest["projectId"],
        "repository": REPO, "branch": BRANCH, "runId": run_id,
        "releaseId": RELEASE_ID, "assetId": ASSET_ID, "releaseTag": TAG,
        "releaseDraft": True, "appId": manifest["appId"],
        "versionName": "1.0.0", "versionCode": 1,
        "apkFile": APK_NAME, "apkBytes": APK_BYTES, "apkSha256": APK_SHA,
        "certificateSha256": CERT_SHA, "manifestSha256": sha(raw),
        "isolatedUnityProjectCommit": SOURCE_COMMIT,
        "buildScriptPatchSha256": BUILD_SCRIPT_PATCH_SHA,
        "riftHudSha256": RIFT_HUD_SHA, "riftGameSha256": RIFT_GAME_SHA,
        "resourcesMetaSha256": RESOURCES_META_SHA,
        "riftUrpLitMaterialSha256": RIFT_URP_LIT_SHA,
        "riftUrpLitMaterialMetaSha256": RIFT_URP_LIT_META_SHA,
        "linkXmlSha256": LINK_XML_SHA,
        "linkXmlMetaSha256": LINK_XML_META_SHA,
        "storeWrites": 0, "firebaseWrites": 0, "signerSecretsUsed": False,
    }
    (dest / "fetch-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "EXACT_RIFT_DRAFT_APK_FETCH_VERIFIED",
                      "apkSha256": APK_SHA, "manifestSha256": provenance["manifestSha256"]}))


if __name__ == "__main__":
    main()
