"""Isolated official Linux SDK setup for the one fixed Crack2 KVM run."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

URL = "https://dl.google.com/android/repository/emulator-linux_x64-16428233.zip"
SIZE = 349654171
SHA1 = "cd7362ea55dfb86a418958138dc396e74165dd01"


def main():
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != "mars-tw/taiwan-train-math"
            or os.environ.get("GITHUB_REF") != "refs/heads/codex/crack2-kvm-qa-20261013-r11"):
        raise RuntimeError("Fixed Crack QA branch only")
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    sdk = temp / "crack-code2-sdk"
    if sdk.exists():
        raise RuntimeError("Fresh own SDK required")
    vendor = Path(os.environ["ANDROID_HOME"]).resolve()
    tools = vendor / "cmdline-tools/latest"
    if not (tools / "bin/sdkmanager").is_file() or not (vendor / "licenses").is_dir():
        raise RuntimeError("Official runner command-line tools and existing accepted licenses required")
    sdk.mkdir()
    (temp / "crack-code2-avds").mkdir(mode=0o700)
    (temp / "crack-code2-user").mkdir(mode=0o700)
    shutil.copytree(tools, sdk / "cmdline-tools/latest", symlinks=True)
    shutil.copytree(vendor / "licenses", sdk / "licenses")
    archive = temp / "crack-official-emulator-16428233.zip"
    with urllib.request.urlopen(URL, timeout=60) as response, archive.open("wb") as out:
        while block := response.read(1024 * 1024):
            out.write(block)
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha1").hexdigest()
    if archive.stat().st_size != SIZE or actual != SHA1:
        raise RuntimeError("Pinned official emulator archive mismatch")
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            path = Path(entry.filename)
            if path.is_absolute() or ".." in path.parts or not entry.filename.startswith("emulator/"):
                raise RuntimeError("Official archive path leaves owned emulator subtree")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                link = package.read(entry).decode()
                if not (sdk / path.parent / link).resolve().is_relative_to(sdk / "emulator"):
                    raise RuntimeError("Official archive symlink leaves owned emulator subtree")
    subprocess.run(["unzip", "-q", str(archive), "-d", str(sdk)], check=True, timeout=90)
    manager = sdk / "cmdline-tools/latest/bin/sdkmanager"
    java = os.environ.get("JAVA_HOME_17_X64")
    if not java or not (Path(java) / "bin/java").is_file():
        raise RuntimeError("Known runner JDK17 required for official command-line SDK tools")
    child_env = os.environ.copy()
    child_env["JAVA_HOME"] = java
    child_env["PATH"] = str(Path(java) / "bin") + ":" + child_env["PATH"]
    subprocess.run([str(manager), "--sdk_root=" + str(sdk), "--install", "platform-tools",
                    "build-tools;36.1.0", "system-images;android-36;google_apis;x86_64", "--channel=0"],
                   check=True, timeout=720, env=child_env)
    image = sdk / "system-images/android-36/google_apis/x86_64"
    properties = dict(line.split("=", 1) for line in (image / "source.properties").read_text().splitlines()
                      if "=" in line and not line.startswith("#"))
    build = (image / "build.prop").read_text()
    if (properties.get("Pkg.Revision") != "7" or properties.get("AndroidVersion.ApiLevel") != "36"
            or properties.get("SystemImage.Abi") != "x86_64"
            or "ro.system.product.cpu.abilist64=x86_64,arm64-v8a" not in build
            or "ro.dalvik.vm.native.bridge=libndk_translation.so" not in build):
        raise RuntimeError("Exact API36 revision7 ARM64-translation image contract differs")
    out = Path(os.environ["GITHUB_WORKSPACE"]) / "output/crack-code2-runtime"
    out.mkdir(parents=True, exist_ok=True)
    (out / "sdk-provenance.json").write_text(json.dumps({"schemaVersion": 1, "projectId": "crackveil-vanguard", "versionCode": 2,
        "gpuModeRequested":"swangle", "environmentExperiment":True, "productShaderFixClaimed":False,
        "fixedApkSha256": "0b3a4aec652ce8cbb5110688670df3ef7d60bce28d13668c3fa6f22d5e54a8d2",
        "rawSourceManifestSha256": "975871052ae1a04944b009957b09afc0db74ced44bcbcfbd66b48bb3a01cdb0a",
        "emulatorArchiveUrl": URL, "emulatorArchiveBytes": SIZE, "emulatorArchiveSha1": actual,
        "emulatorRevision": "37.2.12", "systemImage": "system-images;android-36;google_apis;x86_64",
        "imageRevision": 7, "imageOfficialArchiveUrl": "https://dl.google.com/android/repository/sys-img/google_apis/x86_64-36_r07.zip",
        "imageOfficialArchiveBytes": 1895447397, "imageOfficialArchiveSha1": "c6bf44bdcd885bb902b4ba752d111a073ad7a817",
        "imageSourcePropertiesSha256": hashlib.sha256((image / "source.properties").read_bytes()).hexdigest(),
        "imageBuildPropSha256": hashlib.sha256((image / "build.prop").read_bytes()).hexdigest(),
        "sdkRoot": str(sdk), "avdManager": str(sdk / "cmdline-tools/latest/bin/avdmanager"),
        "canonicalAvdManagerSdkRoot": True, "actualGuestTranslationVerified": False}, indent=2) + "\n")
    with Path(os.environ["GITHUB_ENV"]).open("a") as env:
        env.write(f"CRACK_SDK={sdk}\nANDROID_HOME={sdk}\nANDROID_SDK_ROOT={sdk}\n")
        env.write(f"JAVA_HOME={java}\n")
        env.write(f"ANDROID_AVD_HOME={temp / 'crack-code2-avds'}\nANDROID_USER_HOME={temp / 'crack-code2-user'}\n")
    print("One official isolated emulator/API36-r7 SDK ready; no AVD or game started yet.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            out = Path(os.environ["GITHUB_WORKSPACE"]) / "output/crack-code2-runtime"
            out.mkdir(parents=True, exist_ok=True)
            (out / "bootstrap-failure.json").write_text(json.dumps({"status":"SDK_BOOTSTRAP_FAILED",
                "projectId":"crackveil-vanguard","errorType":type(error).__name__,
                "nativeEmulatorStarted":False,"gameExecuted":False},indent=2)+"\n")
        raise
