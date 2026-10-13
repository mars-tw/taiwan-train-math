#!/usr/bin/env python3
"""Verify Train Math signed APK/AAB identity and bundled source bytes."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile


APP_ID = "tw.mars.trainmath"
VERSION = "1.0.0"
BUILD = 2
BUNDLETOOL_SHA256 = "a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29"
ANDROID = "{http://schemas.android.com/apk/res/android}"
GENERATED_PUBLIC = {"cordova.js", "cordova_plugins.js"}


def fail(message):
    raise SystemExit(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tool_output(args, label):
    result = subprocess.run([str(arg) for arg in args], capture_output=True, timeout=180, check=False)
    if result.returncode:
        fail(f"{label} failed; tool output is intentionally withheld")
    return result.stdout.decode("utf-8", errors="replace")


def expected_files(manifest):
    if manifest.get("appId") != APP_ID or manifest.get("remoteServer") is not False:
        fail("Wrong native source manifest")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        fail("Missing native source files")
    result = {}
    for item in files:
        if not isinstance(item, dict):
            fail("Malformed native source record")
        name = item.get("path")
        size = item.get("bytes")
        sha = item.get("sha256")
        if (not isinstance(name, str) or not name or "\\" in name
                or any(part in {"", ".", ".."} for part in name.split("/"))
                or PurePosixPath(name).is_absolute() or name in result
                or type(size) is not int or size < 0
                or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha)):
            fail("Unsafe or duplicate native source record")
        result[name] = {"bytes": size, "sha256": sha}
    if manifest.get("bytes") != sum(item["bytes"] for item in result.values()):
        fail("Native source byte total differs")
    return result


def check_payload(archive_path, prefix, expected):
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            fail("Duplicate signed package entry")
        actual = {name[len(prefix):] for name in names if name.startswith(prefix) and not name.endswith("/")}
        generated = actual - set(expected)
        if set(expected) - actual or generated - GENERATED_PUBLIC:
            fail("Signed package source asset set differs")
        for name, record in expected.items():
            member = prefix + name
            item = archive.getinfo(member)
            if item.file_size != record["bytes"]:
                fail("Signed package source asset size differs")
            with archive.open(item) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
                    fail("Signed package source asset hash differs")
        extras = {}
        for name in generated:
            with archive.open(prefix + name) as stream:
                extras[name] = hashlib.file_digest(stream, "sha256").hexdigest()
        return extras


def main():
    parser = argparse.ArgumentParser()
    for name in ("apk", "aab", "manifest", "aapt", "java", "bundletool", "receipt"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    for name in ("apk", "aab", "manifest", "aapt", "java", "bundletool"):
        path = getattr(args, name)
        if path.is_symlink() or not path.is_file():
            fail(f"Missing or linked verification input: {name}")
    if args.receipt.exists():
        fail("Refusing to overwrite Android verification receipt")
    if digest(args.bundletool) != BUNDLETOOL_SHA256:
        fail("bundletool digest is not the reviewed 1.18.3 binary")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    files = expected_files(manifest)

    badging = tool_output([args.aapt, "dump", "badging", args.apk], "APK badging")
    expected_badging = f"package: name='{APP_ID}' versionCode='{BUILD}' versionName='{VERSION}'"
    if expected_badging not in badging or "application-debuggable" in badging:
        fail("Signed APK identity, version, or release state differs")
    xml = ET.fromstring(tool_output([args.java, "-jar", args.bundletool, "dump", "manifest",
                                     "--bundle=" + str(args.aab), "--module=base"], "AAB manifest"))
    application = xml.find("application")
    if (xml.get("package") != APP_ID or xml.get(ANDROID + "versionCode") != str(BUILD)
            or xml.get(ANDROID + "versionName") != VERSION or application is None
            or application.get(ANDROID + "debuggable", "false") != "false"):
        fail("Signed AAB identity, version, or release state differs")

    apk_extras = check_payload(args.apk, "assets/public/", files)
    aab_extras = check_payload(args.aab, "base/assets/public/", files)
    if apk_extras != aab_extras:
        fail("Generated native assets differ between signed APK and AAB")
    receipt = {"appId": APP_ID, "version": VERSION, "build": BUILD,
               "bundletoolSha256": BUNDLETOOL_SHA256,
               "sourceManifestSha256": digest(args.manifest),
               "payloadFilesVerifiedInBoth": len(files),
               "signedApkAndAabSourceEquivalent": True,
               "signedApkSha256": digest(args.apk), "signedAabSha256": digest(args.aab)}
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Signed APK and AAB identity and source payload verified")


if __name__ == "__main__":
    main()
