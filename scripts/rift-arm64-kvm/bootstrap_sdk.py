"""Provision one isolated official API 36 KVM SDK for Rift's ARM64 APK."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request
import zipfile

from fetch_input import BRANCH, REPO, SYSTEM_IMAGE, read_manifest


EMULATOR_URL = "https://dl.google.com/android/repository/emulator-linux_x64-16428233.zip"
EMULATOR_BYTES = 349_654_171
EMULATOR_SHA1 = "cd7362ea55dfb86a418958138dc396e74165dd01"
IMAGE_URL = "https://dl.google.com/android/repository/sys-img/google_apis/x86_64-36_r07.zip"
IMAGE_BYTES = 1_895_447_397
IMAGE_SHA1 = "c6bf44bdcd885bb902b4ba752d111a073ad7a817"
OWNER = "rift-arm64-kvm-r5"


def read_properties(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                if "=" in line and not line.startswith("#"))


def verify_image_contract(properties: dict[str, str], build: str) -> None:
    if (properties.get("Pkg.Revision") != "7"
            or properties.get("AndroidVersion.ApiLevel") != "36"
            or properties.get("SystemImage.Abi") != "x86_64"
            or "ro.system.product.cpu.abilist64=x86_64,arm64-v8a" not in build.splitlines()
            or "ro.dalvik.vm.native.bridge=libndk_translation.so" not in build.splitlines()):
        raise RuntimeError("Official API36 revision7 ARM64 bridge contract differs")


def self_test() -> None:
    manifest, _ = read_manifest()
    if manifest["runtime"]["image"] != SYSTEM_IMAGE:
        raise AssertionError("Rift manifest image differs")
    sample = {"Pkg.Revision": "7", "AndroidVersion.ApiLevel": "36", "SystemImage.Abi": "x86_64"}
    build = "ro.system.product.cpu.abilist64=x86_64,arm64-v8a\nro.dalvik.vm.native.bridge=libndk_translation.so\n"
    verify_image_contract(sample, build)
    try:
        verify_image_contract(sample, build.replace("arm64-v8a", ""))
    except RuntimeError:
        pass
    else:
        raise AssertionError("Absent ARM64 bridge accepted")
    print(json.dumps({"status": "RIFT_SDK_CONTRACT_SELF_TEST_PASSED", "networkUsed": False}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    manifest, _ = read_manifest()
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != REPO
            or os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCH
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"):
        raise RuntimeError("One original run on the dedicated Rift QA branch only")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    head_sha = os.environ.get("GITHUB_SHA", "")
    if (not re.fullmatch(r"[1-9][0-9]{0,19}", run_id)
            or not re.fullmatch(r"[0-9a-f]{40}", head_sha)):
        raise RuntimeError("Invalid exact owned run identity")
    raw_temp = os.environ.get("RUNNER_TEMP", "")
    raw_workspace = os.environ.get("GITHUB_WORKSPACE", "")
    raw_vendor = os.environ.get("ANDROID_HOME", "")
    if not all(os.path.isabs(p) for p in (raw_temp, raw_workspace, raw_vendor)):
        raise RuntimeError("Absolute runner temp/workspace/vendor SDK required")
    temp = Path(raw_temp)
    workspace = Path(raw_workspace)
    vendor = Path(raw_vendor)
    if any(p.is_symlink() for p in (temp, workspace, vendor)):
        raise RuntimeError("Runner root paths may not be linked")
    temp = temp.resolve()
    workspace = workspace.resolve()
    vendor = vendor.resolve()
    sdk = temp / "rift-arm64-kvm-r5-sdk"
    if sdk.exists() or sdk.is_symlink():
        raise RuntimeError("Fresh owned SDK required; no overwrite or retry")
    tools = vendor / "cmdline-tools/latest"
    licenses = vendor / "licenses"
    if (not (tools / "bin/sdkmanager").is_file()
            or not licenses.is_dir()
            or not (licenses / "android-sdk-license").is_file()):
        raise RuntimeError("Official runner SDK tools and previously accepted licenses required")
    java = os.environ.get("JAVA_HOME_17_X64", "")
    if not java or not (Path(java) / "bin/java").is_file():
        raise RuntimeError("Known runner JDK 17 required for official command-line tools")
    sdk.mkdir()
    shutil.copytree(tools, sdk / "cmdline-tools/latest", symlinks=True)
    shutil.copytree(licenses, sdk / "licenses")
    archive = temp / "rift-arm64-kvm-r5-official-emulator-16428233.zip"
    if archive.exists() or archive.is_symlink():
        raise RuntimeError("Owned official emulator archive already exists")
    with urllib.request.urlopen(EMULATOR_URL, timeout=60) as response, archive.open("xb") as out:
        while block := response.read(1024 * 1024):
            out.write(block)
    with archive.open("rb") as stream:
        actual_sha1 = hashlib.file_digest(stream, "sha1").hexdigest()
    if archive.stat().st_size != EMULATOR_BYTES or actual_sha1 != EMULATOR_SHA1:
        raise RuntimeError("Pinned official emulator archive differs")
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            path = Path(entry.filename)
            if path.is_absolute() or ".." in path.parts or not entry.filename.startswith("emulator/"):
                raise RuntimeError("Official archive entry leaves owned emulator subtree")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                link = package.read(entry).decode("utf-8")
                if not (sdk / path.parent / link).resolve().is_relative_to(sdk / "emulator"):
                    raise RuntimeError("Official archive symlink leaves owned emulator subtree")
    subprocess.run(["unzip", "-q", str(archive), "-d", str(sdk)], check=True, timeout=90)
    manager = sdk / "cmdline-tools/latest/bin/sdkmanager"
    child_env = os.environ.copy()
    child_env["JAVA_HOME"] = java
    child_env["PATH"] = str(Path(java) / "bin") + ":" + child_env["PATH"]
    # Copy existing runner licenses only. A new legal prompt gets EOF and fails.
    subprocess.run([str(manager), "--sdk_root=" + str(sdk), "--install", "platform-tools",
                    "build-tools;36.1.0", SYSTEM_IMAGE, "--channel=0"],
                   check=True, timeout=720, env=child_env, stdin=subprocess.DEVNULL)
    image = sdk / "system-images/android-36/google_apis/x86_64"
    properties_path = image / "source.properties"
    build_path = image / "build.prop"
    verify_image_contract(read_properties(properties_path), build_path.read_text(encoding="utf-8"))
    if read_properties(sdk / "emulator/source.properties").get("Pkg.Revision") != "37.2.12":
        raise RuntimeError("Pinned official emulator version differs")
    if read_properties(sdk / "build-tools/36.1.0/source.properties").get("Pkg.Revision") != "36.1.0":
        raise RuntimeError("Pinned official build tools version differs")
    output_parent = workspace / "output"
    output = output_parent / OWNER
    if (output_parent.is_symlink() or output.exists() or output.is_symlink()
            or not output.is_relative_to(workspace)):
        raise RuntimeError("Owned evidence output already exists or is linked")
    output.mkdir(parents=True, exist_ok=False)
    (output / "owned-run.json").write_text(json.dumps({
        "runId": run_id, "headSha": head_sha, "owner": OWNER}, indent=2) + "\n", encoding="utf-8")
    provenance = {
        "schemaVersion": 1, "projectId": manifest["projectId"],
        "emulatorArchiveUrl": EMULATOR_URL, "emulatorArchiveBytes": EMULATOR_BYTES,
        "emulatorArchiveSha1": actual_sha1, "emulatorRevision": "37.2.12",
        "systemImage": SYSTEM_IMAGE, "imageRevision": 7,
        "imageOfficialArchiveUrl": IMAGE_URL, "imageOfficialArchiveBytes": IMAGE_BYTES,
        "imageOfficialArchiveSha1": IMAGE_SHA1,
        "imageSourcePropertiesSha256": hashlib.sha256(properties_path.read_bytes()).hexdigest(),
        "imageBuildPropSha256": hashlib.sha256(build_path.read_bytes()).hexdigest(),
        "sdkRoot": str(sdk), "avdManager": str(sdk / "cmdline-tools/latest/bin/avdmanager"),
        "licensesCopiedFromExistingRunner": True, "sdkmanagerLicenseAcceptanceRun": False,
        "runnerSdkLicenseSha256": hashlib.sha256((licenses / "android-sdk-license").read_bytes()).hexdigest(),
        "canonicalAvdManagerSdkRoot": True, "actualGuestTranslationVerified": False,
        "isolatedUnityProjectCommit": manifest["source"]["isolatedUnityProjectCommit"],
        "buildScriptPatchSha256": manifest["source"]["buildScriptPatchSha256"],
        "riftHudSha256": manifest["source"]["riftHudSha256"],
        "riftGameSha256": manifest["source"]["riftGameSha256"],
        "resourcesMetaSha256": manifest["source"]["resourcesMetaSha256"],
        "riftUrpLitMaterialSha256": manifest["source"]["riftUrpLitMaterialSha256"],
        "riftUrpLitMaterialMetaSha256": manifest["source"]["riftUrpLitMaterialMetaSha256"],
        "linkXmlSha256": manifest["source"]["linkXmlSha256"],
        "linkXmlMetaSha256": manifest["source"]["linkXmlMetaSha256"],
    }
    (output / "sdk-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as env:
        env.write(f"RIFT_SDK={sdk}\nANDROID_HOME={sdk}\nANDROID_SDK_ROOT={sdk}\n")
        env.write(f"JAVA_HOME={java}\n")
        env.write(f"ANDROID_AVD_HOME={temp / 'rift-arm64-kvm-r5-avds'}\n")
        env.write(f"ANDROID_USER_HOME={temp / 'rift-arm64-kvm-r5-user'}\n")
        env.write(f"RIFT_APK={temp / 'rift-arm64-kvm-r5-input/RiftForge-dev-primitive-fix.apk'}\n")
        env.write(f"RIFT_OUTPUT={output}\n")
    print(json.dumps({"status": "ISOLATED_RIFT_API36_ARM64_BRIDGE_SDK_READY",
                      "sdkRoot": str(sdk), "gameStarted": False, "legalPromptAccepted": False}))


if __name__ == "__main__":
    main()
