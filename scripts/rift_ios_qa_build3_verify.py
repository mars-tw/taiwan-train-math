#!/usr/bin/env python3
"""Pin, extract and verify Rift QA3 Xcode source or a signed device QA IPA."""

import argparse
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat
import zipfile

APP_ID = "tw.mars.riftforge3d"
TEAM_ID = "93L76Q5PT8"
SOURCE_COMMIT = "cd9a6e3d3a8f7a63dca22fbb05d5d32d48f774f7"
SOURCE_TREE = "b2d5de5fc95358a1667fb75532183587b5b35dd7"
ZIP_SHA256 = "d7bc46b1668518fb1235be70307976ae39eb72fc9dcbe2794dae88d4f74bc828"
MANIFEST_SHA256 = "3c1855883b34904a48c517d4c63660265e6ec7bbc0679b0661dc4b1b3d8d65db"
BRAND_SHA256 = "4b892d749cc4de40fd6eda9d7eabc13da689a6d78ab913d0c0a69129cebbf776"
INFO_SHA256 = "b7cccc9e00c210d8d30f0037f169ae7fc1ec81ec042cd79ef6078ebed8e52000"
PBX_SHA256 = "f66c4941222b067cddf1d3c3f7ef864b10b866169f9e2f679c641eb161665c7e"
IOS_BUILDER_SHA256 = "3c76f792f252b5ce38dec6aab7a55f655d3c93282b51bc48b4c961ba2a67ca39"
PROFILE_SHA256 = "b6eab8c786950d77f64b842b87050381cca26d4a0b79c53f0619f0d262d08c52"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fail(message):
    raise SystemExit(message)


def safe_name(name):
    parts = name.split("/")
    return bool(name and not name.startswith("/") and "\\" not in name
                and ":" not in name and not any(part in ("", ".", "..") for part in parts))


def source(args):
    archive = Path(args.zip).resolve(strict=True)
    manifest_path = Path(args.manifest).resolve(strict=True)
    brand_path = Path(args.brand).resolve(strict=True)
    destination = Path(args.destination).resolve()
    receipt_path = Path(args.receipt).resolve()
    if any(path.is_symlink() for path in (archive, manifest_path, brand_path)):
        fail("Linked source input rejected")
    if (digest(archive), digest(manifest_path), digest(brand_path)) != (
            ZIP_SHA256, MANIFEST_SHA256, BRAND_SHA256):
        fail("Pinned QA3 Xcode source checksum differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    brand = json.loads(brand_path.read_text(encoding="utf-8"))
    if (manifest.get("projectId") != "rift-forge-3d"
            or manifest.get("sourceCommit") != SOURCE_COMMIT
            or manifest.get("sourceGitTree") != SOURCE_TREE
            or manifest.get("iosEditorTransformSha256") != IOS_BUILDER_SHA256
            or manifest.get("appId") != APP_ID
            or manifest.get("version") != "1.0.0" or manifest.get("build") != 3
            or manifest.get("signed") is not False
            or manifest.get("readyForStore") is not False
            or manifest.get("developmentQa") is not True
            or manifest.get("xcodeArchiveSha256") != ZIP_SHA256
            or manifest.get("brandTransformSha256") != BRAND_SHA256
            or manifest.get("infoPlistSha256") != INFO_SHA256
            or manifest.get("projectPbxprojSha256") != PBX_SHA256
            or manifest.get("il2cppHoldStrikePresent") is not True
            or brand.get("afterSha256") != INFO_SHA256
            or brand.get("sourceCommit") != SOURCE_COMMIT
            or brand.get("changes") != {
                "CFBundleDisplayName": ["rift-forge-3d", "Rift Forge 3D"],
                "CFBundleName": ["${PRODUCT_NAME}", "Rift Forge 3D"]}):
        fail("QA3 source identity, provenance or brand transform differs")
    records = manifest.get("files")
    if not isinstance(records, list) or len(records) != 3304 or destination.exists() or receipt_path.exists():
        fail("QA3 source inventory or fresh output path differs")
    expected = {item.get("path"): item for item in records}
    if len(expected) != len(records):
        fail("Duplicate manifest member")

    destination.mkdir(parents=True)
    checked = 0
    with zipfile.ZipFile(archive) as package:
        members = [item for item in package.infolist() if not item.is_dir()]
        names = [item.filename for item in members]
        if names != [item["path"] for item in records] or len(names) != len(set(names)):
            fail("QA3 Xcode archive inventory differs")
        for member in members:
            name = member.filename
            record = expected[name]
            if (not safe_name(name) or stat.S_ISLNK(member.external_attr >> 16)
                    or member.file_size != record.get("bytes")
                    or not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", ""))):
                fail("Unsafe or mismatched QA3 Xcode member")
            target = destination.joinpath(*PurePosixPath(name).parts)
            if not target.resolve().is_relative_to(destination):
                fail("QA3 Xcode member escapes extraction root")
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(member) as inp, target.open("xb") as out:
                hash_state = hashlib.sha256()
                for block in iter(lambda: inp.read(1024 * 1024), b""):
                    out.write(block)
                    hash_state.update(block)
            if hash_state.hexdigest() != record["sha256"]:
                fail("QA3 Xcode member digest differs: " + name)
            checked += 1
    info_path = destination / "Info.plist"
    project_path = destination / "Unity-iPhone.xcodeproj/project.pbxproj"
    if digest(info_path) != INFO_SHA256 or digest(project_path) != PBX_SHA256:
        fail("Pinned Info.plist or Xcode project differs")
    info = plistlib.loads(info_path.read_bytes())
    pbx = project_path.read_text(encoding="utf-8")
    if (info.get("CFBundleDisplayName") != "Rift Forge 3D"
            or info.get("CFBundleName") != "Rift Forge 3D"
            or info.get("CFBundleIdentifier") != "${PRODUCT_BUNDLE_IDENTIFIER}"
            or info.get("CFBundleShortVersionString") != "1.0.0"
            or info.get("CFBundleVersion") != "3"
            or "PRODUCT_BUNDLE_IDENTIFIER = " + APP_ID + ";" not in pbx
            or not (destination / "Data/level0").is_file()
            or "HoldStrikeButton" not in (destination / "Il2CppOutputProject/Source/il2cppOutput/RiftForge.Runtime.cpp").read_text(encoding="utf-8")):
        fail("QA3 game identity, scene or hold-STRIKE code unavailable")
    receipt = {"sourceVerified": True, "sourceCommit": SOURCE_COMMIT,
               "sourceZipSha256": ZIP_SHA256, "sourceManifestSha256": MANIFEST_SHA256,
               "brandTransformSha256": BRAND_SHA256, "sourceGitTree": SOURCE_TREE,
               "fileCount": checked, "appId": APP_ID, "version": "1.0.0", "build": 3,
               "signed": False, "physicalDeviceTested": False, "storeUploaded": False,
               "storeReady": False}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Pinned Rift QA3 Xcode source verified; no Apple secret used")


def profile_payload(blob):
    start = blob.find(b"<?xml")
    end = blob.find(b"</plist>", start)
    if start < 0 or end < 0:
        fail("Embedded profile plist unavailable")
    return plistlib.loads(blob[start:end + len(b"</plist>")])


def ipa(args):
    path = Path(args.ipa).resolve(strict=True)
    receipt_path = Path(args.receipt).resolve()
    if path.is_symlink() or receipt_path.exists():
        fail("IPA must be a real file and receipt path must be fresh")
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        apps = {name.split("/")[1] for name in names
                if name.startswith("Payload/") and name.split("/")[1].endswith(".app")}
        if len(apps) != 1:
            fail("IPA has no unique device app")
        prefix = "Payload/" + apps.pop() + "/"
        info = plistlib.loads(package.read(prefix + "Info.plist"))
        profile_bytes = package.read(prefix + "embedded.mobileprovision")
        profile = profile_payload(profile_bytes)
        if not any(name.startswith(prefix + "Frameworks/UnityFramework.framework/") for name in names):
            fail("Signed IPA lacks UnityFramework")
    entitlements = profile.get("Entitlements", {})
    expiration = profile.get("ExpirationDate")
    if (info.get("CFBundleIdentifier") != APP_ID
            or info.get("CFBundleDisplayName") != "Rift Forge 3D"
            or info.get("CFBundleShortVersionString") != "1.0.0"
            or info.get("CFBundleVersion") != "3"
            or profile.get("TeamIdentifier") != [TEAM_ID]
            or hashlib.sha256(profile_bytes).hexdigest() != PROFILE_SHA256
            or entitlements.get("application-identifier") != TEAM_ID + "." + APP_ID
            or entitlements.get("get-task-allow") is not False
            or bool(profile.get("ProvisionedDevices"))
            or not isinstance(expiration, datetime.datetime)
            or expiration <= datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)):
        fail("Signed QA3 IPA identity or profile differs")
    certs = profile.get("DeveloperCertificates")
    if not isinstance(certs, list) or len(certs) != 1:
        fail("Rift profile certificate count differs")
    receipt = {"status": "IPA_STRUCTURE_AND_PROFILE_VERIFIED", "appId": APP_ID,
               "version": "1.0.0", "build": 3, "ipaBytes": path.stat().st_size,
               "ipaSha256": digest(path), "profileUuid": profile.get("UUID"),
               "profileSha256": PROFILE_SHA256,
               "profileCertificateSha1": hashlib.sha1(certs[0]).hexdigest(),
               "sourceCommit": SOURCE_COMMIT, "sourceZipSha256": ZIP_SHA256,
               "physicalDeviceTested": False, "storeUploaded": False, "storeReady": False}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Rift QA3 IPA structure/profile verified; physical QA remains pending")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    p_source = commands.add_parser("source")
    for flag in ("zip", "manifest", "brand", "destination", "receipt"):
        p_source.add_argument("--" + flag, required=True)
    p_source.set_defaults(func=source)
    p_ipa = commands.add_parser("ipa")
    p_ipa.add_argument("--ipa", required=True)
    p_ipa.add_argument("--receipt", required=True)
    p_ipa.set_defaults(func=ipa)
    args = parser.parse_args()
    args.func(args)
