#!/usr/bin/env python3
"""Verify the pinned Rift Forge Unity iOS QA source and signed device IPA.

The source archive is a Development Xcode export from Rift commit a853100.
Its generated Info.plist was changed only to display the game name and use
build number 1. This verifier never treats it as a store-ready release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import plistlib
import re
import stat
import sys
import zipfile

APP_ID = "tw.mars.riftforge3d"
TEAM_ID = "93L76Q5PT8"
SOURCE_COMMIT = "a85310033f3d035b12b0721582f1e85aa56767ad"
ZIP_SHA256 = "a0b19a40c84a4caf0f652a6cf3cb4fa632a8598becbe1f04e78a3c29ffe3bdc3"
MANIFEST_SHA256 = "70501a00e369fd784942739fbc774270b63ba33796a1b2485a46241b3b27e3ae"
TRANSFORM_SHA256 = "d23b0152e8aa7075d9ddd1ea1721e74ee6f489c835e741ffdba1c1846a9337f9"
INFO_SHA256 = "8545173616e7ebbecf38e397dd123976b06dab536623c18ff25544918d36d96b"


def digest(path: pathlib.Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise SystemExit(message)


def safe_name(name: str) -> bool:
    parts = name.split("/")
    return bool(name and not name.startswith("/") and "\\" not in name
                and ":" not in name and not any(part in ("", ".", "..") for part in parts))


def profile_payload(blob: bytes) -> dict:
    # A mobileprovision is a signed CMS envelope containing an XML plist.
    start = blob.find(b"<?xml")
    end = blob.find(b"</plist>", start)
    if start < 0 or end < 0:
        fail("Provisioning profile plist is unavailable")
    return plistlib.loads(blob[start:end + len(b"</plist>")])


def source(args: argparse.Namespace) -> None:
    archive = pathlib.Path(args.zip).resolve(strict=True)
    manifest_path = pathlib.Path(args.manifest).resolve(strict=True)
    transform_path = pathlib.Path(args.transform).resolve(strict=True)
    destination = pathlib.Path(args.destination).resolve()
    receipt_path = pathlib.Path(args.receipt).resolve()
    if any(path.is_symlink() for path in (archive, manifest_path, transform_path)):
        fail("Linked input rejected")
    if (digest(archive) != ZIP_SHA256
            or digest(manifest_path) != MANIFEST_SHA256
            or digest(transform_path) != TRANSFORM_SHA256):
        fail("One or more pinned source digests differ")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    transform = json.loads(transform_path.read_text(encoding="utf-8"))
    if (manifest.get("sourceCommit") != SOURCE_COMMIT
            or manifest.get("kind") != "UNITY_IOS_DEVELOPMENT_XCODE_PROJECT_QA_BRANDED_BUILD1_UNSIGNED"
            or manifest.get("archiveSha256") != ZIP_SHA256
            or manifest.get("fileCount") != 3304
            or manifest.get("signed") is not False
            or manifest.get("xcodeCompiled") is not False
            or transform.get("sourceCommit") != SOURCE_COMMIT
            or transform.get("afterSha256") != INFO_SHA256
            or transform.get("storeReady") is not False):
        fail("Source or transform provenance differs")
    expected = manifest.get("files")
    if not isinstance(expected, list) or len(expected) != 3304:
        fail("Expected file list is incomplete")
    if destination.exists() or receipt_path.exists():
        fail("Fresh source and receipt paths are required")
    destination.mkdir(parents=True)
    checked = 0
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        if names != [item.get("path") for item in expected] or len(names) != len(set(names)):
            fail("Archive members differ from frozen manifest")
        for member, item in zip(package.infolist(), expected):
            name = item["path"]
            if not safe_name(name) or member.is_dir() or stat.S_ISLNK(member.external_attr >> 16):
                fail("Unsafe archive member")
            if member.file_size != item.get("bytes") or not isinstance(item.get("sha256"), str):
                fail("Archive member size/hash descriptor differs")
            target = destination.joinpath(*pathlib.PurePosixPath(name).parts)
            if not target.resolve().is_relative_to(destination):
                fail("Archive path escapes destination")
            target.parent.mkdir(parents=True, exist_ok=True)
            hash_state = hashlib.sha256()
            with package.open(member) as inp, target.open("xb") as output:
                for block in iter(lambda: inp.read(1024 * 1024), b""):
                    hash_state.update(block)
                    output.write(block)
            if hash_state.hexdigest() != item["sha256"]:
                fail("Archive payload digest differs: " + name)
            checked += 1
    info_path = destination / "Info.plist"
    pbx_path = destination / "Unity-iPhone.xcodeproj" / "project.pbxproj"
    if digest(info_path) != INFO_SHA256:
        fail("Generated Info.plist differs from approved QA transform")
    info = plistlib.loads(info_path.read_bytes())
    pbx = pbx_path.read_text(encoding="utf-8")
    if (info.get("CFBundleDisplayName") != "Rift Forge 3D"
            or info.get("CFBundleName") != "Rift Forge 3D"
            or info.get("CFBundleShortVersionString") != "1.0.0"
            or info.get("CFBundleVersion") != "1"
            or info.get("CFBundleIdentifier") != "${PRODUCT_BUNDLE_IDENTIFIER}"
            or "PRODUCT_BUNDLE_IDENTIFIER = " + APP_ID + ";" not in pbx
            or not (destination / "Data" / "level0").is_file()):
        fail("QA branding, identity or playable scene is unavailable")
    receipt = {
        "sourceVerified": True,
        "sourceCommit": SOURCE_COMMIT,
        "sourceZipSha256": ZIP_SHA256,
        "sourceManifestSha256": MANIFEST_SHA256,
        "transformSha256": TRANSFORM_SHA256,
        "fileCount": checked,
        "appId": APP_ID,
        "version": "1.0.0",
        "build": 1,
        "signed": False,
        "storeReady": False,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Pinned Unity iOS QA Xcode source verified; no signing or store upload")


def ipa(args: argparse.Namespace) -> None:
    path = pathlib.Path(args.ipa).resolve(strict=True)
    receipt_path = pathlib.Path(args.receipt).resolve()
    if path.is_symlink() or receipt_path.exists():
        fail("IPA must be a real file and receipt path must be fresh")
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        apps = {name.split("/")[1] for name in names
                if name.startswith("Payload/") and name.split("/")[1].endswith(".app")}
        if len(apps) != 1:
            fail("IPA has no unique device app")
        app = apps.pop()
        prefix = "Payload/" + app + "/"
        info = plistlib.loads(package.read(prefix + "Info.plist"))
        profile = profile_payload(package.read(prefix + "embedded.mobileprovision"))
        if not any(name.startswith(prefix + "Frameworks/UnityFramework.framework/") for name in names):
            fail("UnityFramework is absent")
    entitlements = profile.get("Entitlements", {})
    if (info.get("CFBundleIdentifier") != APP_ID
            or info.get("CFBundleDisplayName") != "Rift Forge 3D"
            or info.get("CFBundleShortVersionString") != "1.0.0"
            or info.get("CFBundleVersion") != "1"
            or profile.get("TeamIdentifier") != [TEAM_ID]
            or entitlements.get("application-identifier") != TEAM_ID + "." + APP_ID
            or entitlements.get("get-task-allow") is not False
            or bool(profile.get("ProvisionedDevices"))):
        fail("Signed IPA identity or App Store profile differs")
    certificates = profile.get("DeveloperCertificates")
    if not isinstance(certificates, list) or len(certificates) != 1:
        fail("Profile certificate count differs")
    receipt = {
        "status": "IPA_STRUCTURE_AND_PROFILE_VERIFIED",
        "appId": APP_ID,
        "version": "1.0.0",
        "build": 1,
        "ipaBytes": path.stat().st_size,
        "ipaSha256": digest(path),
        "profileUuid": profile.get("UUID"),
        "profileCertificateSha1": hashlib.sha1(certificates[0]).hexdigest(),
        "sourceCommit": SOURCE_COMMIT,
        "physicalDeviceTested": False,
        "storeUploaded": False,
        "storeReady": False,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Rift iOS QA IPA identity/profile verified; physical runtime remains pending")


def main() -> None:
    parser = argparse.ArgumentParser()
    command = parser.add_subparsers(dest="command", required=True)
    p_source = command.add_parser("source")
    for flag in ("zip", "manifest", "transform", "destination", "receipt"):
        p_source.add_argument("--" + flag, required=True)
    p_source.set_defaults(func=source)
    p_ipa = command.add_parser("ipa")
    p_ipa.add_argument("--ipa", required=True)
    p_ipa.add_argument("--receipt", required=True)
    p_ipa.set_defaults(func=ipa)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
