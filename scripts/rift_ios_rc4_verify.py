#!/usr/bin/env python3
"""Verify withheld Rift iOS RC4 Xcode source or its signed IPA."""

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
ZIP_SHA256 = "99f8dddbabc300b064d47ba7a83338e2dbcc8d61a5bb50552167d97518ef266b"
MANIFEST_SHA256 = "a159d8db441c15ab53a6eca9a4d5904949a912e0d2e49929312881a60d21c4cb"
BRAND_SHA256 = "e75475f36953f519a470aaa7ee27284470226a8708b2caa81816c18f3ce2c265"
DIFF_SHA256 = "32f89df5143e3d59d7172031086b76e1a9f847973e1c9e230d049504a82f75f5"
CONFIG_SHA256 = "9dc0bb08cdd70bfa4108fdacab4a51ee46c4e2c5f96fcf9951c8cf8155ea4793"
INFO_SHA256 = "32276b3d535d7434086177c8944165b6556bc80c040e2d34906b7f4a4a2ffefa"
PROFILE_SHA256 = "b6eab8c786950d77f64b842b87050381cca26d4a0b79c53f0619f0d262d08c52"
STATUS = "WITHHELD_NOT_UPLOAD_READY"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fail(message):
    raise SystemExit(message)


def safe_name(name):
    parts = name.split("/")
    return bool(name and not name.startswith("/") and "\\" not in name
                and ":" not in name and not any(part in ("", ".", "..") for part in parts))


def no_connections(boot):
    text = boot.decode("utf-8")
    return not (re.search(r"(?im)^player-connection", text)
                or re.search(r"(?im)^wait-for-(native|managed)-debugger\s*=\s*1\s*$", text)
                or re.search(r"(?im)^profiler-", text))


def source(args):
    paths = [Path(getattr(args, field)).resolve(strict=True)
             for field in ("zip", "manifest", "brand", "diff")]
    archive, manifest_path, brand_path, diff_path = paths
    if any(path.is_symlink() for path in paths):
        fail("Linked source input rejected")
    if [digest(path) for path in paths] != [ZIP_SHA256, MANIFEST_SHA256, BRAND_SHA256, DIFF_SHA256]:
        fail("Pinned RC4 source checksum differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    brand = json.loads(brand_path.read_text(encoding="utf-8"))
    patch = diff_path.read_text(encoding="utf-8")
    expected_settings = {
        "Assets/Settings/DefaultVolumeProfile.asset",
        "Assets/Settings/Mobile_RPAsset.asset",
        "Assets/Settings/PC_RPAsset.asset",
        "Assets/Settings/UniversalRenderPipelineGlobalSettings.asset",
        "Assets/_Project/Scripts/Editor/MobileReleaseBuildPreprocessor.cs",
        "ProjectSettings/GraphicsSettings.asset",
        "ProjectSettings/ProjectSettings.asset",
        "ProjectSettings/ShaderGraphSettings.asset",
    }
    settings = manifest.get("worktreeTrackedChanges")
    if (manifest.get("projectId") != "rift-forge-3d"
            or manifest.get("sourceCommit") != SOURCE_COMMIT
            or manifest.get("sourceGitTree") != SOURCE_TREE
            or manifest.get("appId") != APP_ID
            or manifest.get("version") != "1.0.0" or manifest.get("build") != 4
            or manifest.get("developmentBuild") is not False
            or manifest.get("readyForStore") is not False
            or manifest.get("signed") is not False
            or manifest.get("storeUploaded") is not False
            or manifest.get("status") != STATUS
            or manifest.get("canonicalConfigSha256") != CONFIG_SHA256
            or manifest.get("canonicalConfig") != {"sourceStage": "gameplay-unverified", "readyForStore": False}
            or manifest.get("worktreeTrackedDiffSha256") != DIFF_SHA256
            or not isinstance(settings, list) or {s.get("path") for s in settings} != expected_settings
            or manifest.get("runtimeImpactingSetting") != "ProjectSettings/ProjectSettings.asset runInBackground=1 differs from cd9a6e3"
            or "-  runInBackground: 0\n+  runInBackground: 1" not in patch
            or manifest.get("brandTransformSha256") != BRAND_SHA256
            or manifest.get("infoPlistSha256") != INFO_SHA256
            or manifest.get("xcodeArchiveSha256") != ZIP_SHA256
            or manifest.get("xcodeArchiveBytes") != 246663282
            or manifest.get("xcodeFileCount") != 3281
            or brand.get("afterSha256") != INFO_SHA256
            or brand.get("sourceCommit") != SOURCE_COMMIT
            or brand.get("status") != STATUS
            or brand.get("changes") != {
                "CFBundleDisplayName": ["rift-forge-3d", "Rift Forge 3D"],
                "CFBundleName": ["${PRODUCT_NAME}", "Rift Forge 3D"]}):
        fail("RC4 source identity, source diff, or withheld status differs")
    transform = manifest.get("technicalCandidateOverride", {})
    if (transform.get("environment") != "RIFT_TECHNICAL_CANDIDATE=1"
            or transform.get("iosEditorScriptSha256") != "2c0219b0b9f9f6e3234b7cdf9afc6869d084021216d5d199c3d7fd6674a58e1c"
            or transform.get("mobilePreprocessorSha256") != "4f071d90c33549f7d3ed03bcc0e91e866ea6108eedff4971ee4f4f9b9586c3bc"):
        fail("Technical candidate Editor transform differs")
    records = manifest.get("files")
    if not isinstance(records, list) or len(records) != 3281:
        fail("RC4 Xcode file inventory differs")
    names = [item.get("path") for item in records]
    if len(set(names)) != len(names) or not all(safe_name(name) for name in names):
        fail("Duplicate or unsafe Xcode member")
    destination = Path(args.destination).resolve() if args.destination else None
    receipt_path = Path(args.receipt).resolve() if args.receipt else None
    if (destination is not None and destination.exists()) or (receipt_path is not None and receipt_path.exists()):
        fail("RC4 source output path is not fresh")
    if not args.verify_only and (destination is None or receipt_path is None):
        fail("Extraction requires fresh destination and receipt")

    if destination is not None:
        destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as package:
        members = [member for member in package.infolist() if not member.is_dir()]
        if [member.filename for member in members] != names:
            fail("Pinned RC4 Xcode ZIP inventory differs")
        for member, record in zip(members, records):
            if (stat.S_ISLNK(member.external_attr >> 16)
                    or member.file_size != record.get("bytes")
                    or not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", ""))):
                fail("Unsafe or mismatched RC4 Xcode member")
            if destination is not None:
                target = destination.joinpath(*PurePosixPath(member.filename).parts)
                if not target.resolve().is_relative_to(destination):
                    fail("RC4 Xcode member escapes extraction root")
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(member) as inp, target.open("xb") as out:
                    state = hashlib.sha256()
                    for block in iter(lambda: inp.read(1024 * 1024), b""):
                        out.write(block)
                        state.update(block)
                    if state.hexdigest() != record["sha256"]:
                        fail("RC4 Xcode member digest differs: " + member.filename)
            else:
                with package.open(member) as inp:
                    if hashlib.file_digest(inp, "sha256").hexdigest() != record["sha256"]:
                        fail("RC4 Xcode member digest differs: " + member.filename)
        info = plistlib.loads(package.read("Info.plist"))
        pbx = package.read("Unity-iPhone.xcodeproj/project.pbxproj").decode("utf-8")
        boot = package.read("Data/boot.config")
        gameplay = package.read("Il2CppOutputProject/Source/il2cppOutput/RiftForge.Runtime.cpp")
        if (info.get("CFBundleDisplayName") != "Rift Forge 3D"
                or info.get("CFBundleName") != "Rift Forge 3D"
                or info.get("CFBundleShortVersionString") != "1.0.0"
                or info.get("CFBundleVersion") != "4"
                or "PRODUCT_BUNDLE_IDENTIFIER = " + APP_ID + ";" not in pbx
                or not no_connections(boot)
                or hashlib.sha256(boot).hexdigest() != manifest.get("bootConfigSha256")
                or "HoldStrikeButton" not in gameplay.decode("utf-8")
                or "Data/level0" not in names):
            fail("RC4 source content differs or Development connection present")
    if receipt_path is not None:
        receipt = {"sourceVerified": True, "sourceCommit": SOURCE_COMMIT,
                   "sourceGitTree": SOURCE_TREE, "sourceZipSha256": ZIP_SHA256,
                   "sourceManifestSha256": MANIFEST_SHA256,
                   "sourceDiffSha256": DIFF_SHA256, "fileCount": len(records),
                   "appId": APP_ID, "version": "1.0.0", "build": 4,
                   "developmentBuild": False, "signed": False,
                   "physicalDeviceTested": False, "storeUploaded": False,
                   "storeReady": False, "status": STATUS}
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Pinned withheld RC4 Xcode source verified; no Apple secret used")


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
        fail("IPA input or receipt path is unsafe")
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        apps = {name.split("/")[1] for name in names
                if name.startswith("Payload/") and len(name.split("/")) > 2
                and name.split("/")[1].endswith(".app")}
        if len(apps) != 1:
            fail("IPA has no unique device app")
        prefix = "Payload/" + apps.pop() + "/"
        info = plistlib.loads(package.read(prefix + "Info.plist"))
        profile_bytes = package.read(prefix + "embedded.mobileprovision")
        profile = profile_payload(profile_bytes)
        boot = package.read(prefix + "Data/boot.config")
        if (not any(name.startswith(prefix + "Frameworks/UnityFramework.framework/") for name in names)
                or not no_connections(boot)):
            fail("Signed IPA Unity framework missing or Development connection present")
    entitlements = profile.get("Entitlements", {})
    expiration = profile.get("ExpirationDate")
    if (info.get("CFBundleIdentifier") != APP_ID
            or info.get("CFBundleDisplayName") != "Rift Forge 3D"
            or info.get("CFBundleShortVersionString") != "1.0.0"
            or info.get("CFBundleVersion") != "4"
            or profile.get("TeamIdentifier") != [TEAM_ID]
            or hashlib.sha256(profile_bytes).hexdigest() != PROFILE_SHA256
            or entitlements.get("application-identifier") != TEAM_ID + "." + APP_ID
            or entitlements.get("get-task-allow") is not False
            or bool(profile.get("ProvisionedDevices"))
            or not isinstance(expiration, datetime.datetime)
            or expiration <= datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)):
        fail("Signed RC4 IPA identity or profile differs")
    certs = profile.get("DeveloperCertificates")
    if not isinstance(certs, list) or len(certs) != 1:
        fail("Rift distribution profile certificate count differs")
    receipt = {"status": "SIGNED_WITHHELD_RC4_IPA_STRUCTURE_VERIFIED",
               "appId": APP_ID, "version": "1.0.0", "build": 4,
               "ipaBytes": path.stat().st_size, "ipaSha256": digest(path),
               "bootConfigSha256": hashlib.sha256(boot).hexdigest(),
               "profileUuid": profile.get("UUID"), "profileSha256": PROFILE_SHA256,
               "profileCertificateSha1": hashlib.sha1(certs[0]).hexdigest(),
               "sourceCommit": SOURCE_COMMIT, "sourceZipSha256": ZIP_SHA256,
               "developmentBuild": False, "physicalDeviceTested": False,
               "storeUploaded": False, "storeReady": False, "releaseStatus": STATUS}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Signed withheld RC4 IPA structure/profile verified; no store upload")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    p_source = commands.add_parser("source")
    for field in ("zip", "manifest", "brand", "diff"):
        p_source.add_argument("--" + field, required=True)
    p_source.add_argument("--destination")
    p_source.add_argument("--receipt")
    p_source.add_argument("--verify-only", action="store_true")
    p_source.set_defaults(func=source)
    p_ipa = commands.add_parser("ipa")
    p_ipa.add_argument("--ipa", required=True)
    p_ipa.add_argument("--receipt", required=True)
    p_ipa.set_defaults(func=ipa)
    args = parser.parse_args()
    args.func(args)
