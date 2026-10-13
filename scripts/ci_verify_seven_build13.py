"""Verify the pinned Seven District iOS 1.0.0 build 13 source and IPA; no store API calls."""
from __future__ import annotations
import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import pathlib
import plistlib
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import zipfile

PROJECTS = {
    "seven-district-reckoning": ("tw.mars.sevendistrictreckoning", "SevenDistrict"),
}
SOURCE_COMMIT = "b9377588c91b95bba81e98c343e51886f3d38b01"
PCK_SHA256 = "adb2466826ce250b8b357b706b3520c9e69792a2fceb06da5bbd3f724a9f9439"
REASONS = {
    "NSPrivacyAccessedAPICategoryFileTimestamp": {"DDA9.1", "C617.1"},
    "NSPrivacyAccessedAPICategorySystemBootTime": {"35F9.1"},
    "NSPrivacyAccessedAPICategoryDiskSpace": {"E174.1", "85F4.1"},
}


def fail(message):
    raise ValueError(message)


def identity(project):
    if project not in PROJECTS:
        fail("Unknown Godot project; identity may not be supplied freely")
    return PROJECTS[project]


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def run(args, timeout=120):
    result = subprocess.run([str(a) for a in args], capture_output=True, timeout=timeout)
    if result.returncode:
        fail("Apple verification command failed; private output withheld")
    return result.stdout


def relative_name(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or value.startswith("/") or any(p in ("", ".", "..") for p in value.split("/")):
        fail("Unsafe source or archive path")
    return pathlib.PurePosixPath(value)


def extract_zip(archive_path, destination, ipa=False):
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        fail("Extraction destination must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        names, total = set(), 0
        for entry in archive.infolist():
            name = entry.filename.rstrip("/")
            path = relative_name(name)
            if name in names or stat.S_ISLNK(entry.external_attr >> 16):
                fail("Duplicate or linked archive entry")
            names.add(name)
            total += entry.file_size
            if total > 2 * 1024**3 or len(names) > 20000:
                fail("Archive exceeds bounded size")
            forbidden = name.lower().endswith((".p8", ".p12", ".pfx", ".pem", ".key", ".keystore", ".mobileprovision", ".log"))
            if forbidden and not (ipa and name.endswith("/embedded.mobileprovision")):
                fail("Private material or raw log in archive")
            target = destination.joinpath(*path.parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open("xb") as out:
                    shutil.copyfileobj(source, out)
                if os.name != "nt":
                    target.chmod((entry.external_attr >> 16) & 0o777 or 0o600)


def privacy(path):
    value = plistlib.loads(path.read_bytes())
    if value.get("NSPrivacyTracking") is not False:
        fail("Godot privacy tracking declaration changed")
    entries = value.get("NSPrivacyAccessedAPITypes", [])
    found = {e.get("NSPrivacyAccessedAPIType"): set(e.get("NSPrivacyAccessedAPITypeReasons", [])) for e in entries}
    if any(not reasons.issubset(found.get(category, set())) for category, reasons in REASONS.items()):
        fail("Godot required-reason declarations are missing")
    return sorted(found)


def verify_source(root, metadata_path, project):
    app_id, name = identity(project)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if (metadata.get("appId") != app_id or metadata.get("nativeVersion") != "1.0.0" or type(metadata.get("nativeBuild")) is not int or metadata.get("nativeBuild") != 13
            or metadata.get("engineVersion") != "4.7.2" or metadata.get("project") != name + ".xcodeproj"
            or metadata.get("scheme") != name or metadata.get("sourceFiles") != 47
            or metadata.get("sourceCommit") != SOURCE_COMMIT or metadata.get("pckSha256") != PCK_SHA256):
        fail("Godot source identity/version/recipe mismatch")
    records = metadata.get("files")
    if not isinstance(records, list) or len(records) != 47:
        fail("Expected the 47 verified source files")
    names = set()
    for item in records:
        relative_name(item.get("path"))
        if item["path"] in names or type(item.get("bytes")) is not int or item["bytes"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")):
            fail("Invalid source hash record")
        names.add(item["path"])
        path = root / item["path"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
            fail("Godot source byte/SHA mismatch")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != names or any(p.is_symlink() for p in root.rglob("*")):
        fail("Missing, extra or linked source file")
    required = {name + ".pck", "PrivacyInfo.xcprivacy", name + ".xcodeproj/project.pbxproj",
                name + ".xcodeproj/xcshareddata/xcschemes/" + name + ".xcscheme", name + ".xcframework/Info.plist", "MoltenVK.xcframework/Info.plist"}
    if not required.issubset(names) or not any(n.startswith(name + ".xcframework/") and n.endswith(".a") for n in names):
        fail("PCK, Xcode scheme or native framework binary is missing")
    if (root / (name + ".pck")).read_bytes()[:4] != b"GDPC":
        fail("Invalid Godot game PCK")
    if digest(root / (name + ".pck")) != PCK_SHA256:
        fail("PCK differs from the reviewed build 13 export")
    pbx = (root / (name + ".xcodeproj/project.pbxproj")).read_text(encoding="utf-8")
    ids = re.findall(r'PRODUCT_BUNDLE_IDENTIFIER\s*=\s*"?([^;"\s]+)"?;', pbx)
    if not ids or any(i != app_id for i in ids) or not re.search(r"MARKETING_VERSION\s*=\s*1\.0\.0;", pbx) or not re.search(r"CURRENT_PROJECT_VERSION\s*=\s*13;", pbx):
        fail("Xcode settings do not bind the approved identity/version")
    categories = privacy(root / "PrivacyInfo.xcprivacy")
    return {"projectId": project, "appId": app_id, "version": "1.0.0", "build": 13, "engineVersion": "4.7.2",
            "sourceFiles": 47, "pckSha256": digest(root / (name + ".pck")), "sourceMetadataSha256": digest(metadata_path),
            "requiredReasonCategories": categories, "sourceVerified": True, "macBuildPerformed": False,
            "signatureVerified": False, "simulatorExecuted": False, "storeUploadPerformed": False}


def verify_zip(source, metadata, project, destination):
    identity(project)
    record = json.loads(metadata.read_text(encoding="utf-8"))
    if record.get("zip", {}).get("sha256") != digest(source) or record.get("zip", {}).get("bytes") != source.stat().st_size:
        fail("Source ZIP differs from the pinned export metadata")
    extract_zip(source, destination)
    return verify_source(destination, metadata, project)


def inspect_profile(path, app_id, team):
    profile = plistlib.loads(run(["security", "cms", "-D", "-i", path]))
    entitlements = profile.get("Entitlements", {})
    prefixes = profile.get("ApplicationIdentifierPrefix", [])
    expiry = profile.get("ExpirationDate")
    if (profile.get("TeamIdentifier") != [team] or not prefixes
            or entitlements.get("application-identifier") != prefixes[0] + "." + app_id
            or entitlements.get("com.apple.developer.team-identifier") != team
            or entitlements.get("get-task-allow") is not False or entitlements.get("beta-reports-active") is not True
            or "ProvisionedDevices" in profile or profile.get("ProvisionsAllDevices") or "iOS" not in profile.get("Platform", [])):
        fail("Wrong per-App App Store distribution profile")
    if not isinstance(expiry, datetime.datetime) or expiry.replace(tzinfo=datetime.timezone.utc) <= datetime.datetime.now(datetime.timezone.utc):
        fail("Expired profile")
    certificates = profile.get("DeveloperCertificates", [])
    if len(certificates) != 1 or not re.fullmatch(r"[A-Fa-f0-9-]{36}", str(profile.get("UUID", ""))) or not profile.get("Name"):
        fail("Profile UUID/name/certificate mismatch")
    return profile, {"uuid": profile["UUID"], "name": profile["Name"], "prefix": prefixes[0],
                     "certificateSha1": hashlib.sha1(certificates[0]).hexdigest().upper(),
                     "certificateSha256": hashlib.sha256(certificates[0]).hexdigest()}


def architectures(path):
    with path.open("rb") as stream:
        head = stream.read(1024)
    if head[:4] in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"):
        endian = "<" if head[0] == 0xcf else ">"
        values = [struct.unpack_from(endian + "I", head, 4)[0]]
    elif head[:4] in (b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"):
        endian = ">" if head[0] == 0xca else "<"
        count = struct.unpack_from(endian + "I", head, 4)[0]
        step = 32 if head[:4] in (b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca") else 20
        if not 1 <= count <= 16 or 8 + count * step > len(head):
            fail("Invalid Mach-O table")
        values = [struct.unpack_from(endian + "I", head, 8 + index * step)[0] for index in range(count)]
    else:
        fail("Missing main Mach-O executable")
    return [{0x0100000C: "arm64", 0x01000007: "x86_64"}.get(v, "unsupported") for v in values]


def inspect_app(app, source, project, device):
    app_id, name = identity(project)
    info = plistlib.loads((app / "Info.plist").read_bytes())
    expected = ["iPhoneOS"] if device else ["iPhoneSimulator"]
    if (info.get("CFBundleIdentifier") != app_id or info.get("CFBundleShortVersionString") != "1.0.0"
            or str(info.get("CFBundleVersion")) != "13" or info.get("CFBundleSupportedPlatforms") != expected
            or info.get("DTXcodeBuild") != "17C529" or not {1, 2}.issubset(set(info.get("UIDeviceFamily", [])))
            or info.get("TestFlightInternalTestingOnly", False)):
        fail("Built Godot App identity/platform/Xcode mismatch")
    sdk = str(info.get("DTSDKName", ""))
    if not re.fullmatch(("iphoneos" if device else "iphonesimulator") + r"(?:2[6-9]|[3-9][0-9])(?:\.[0-9]+)*", sdk):
        fail("Unexpected built SDK")
    pck = app / (name + ".pck")
    if not pck.is_file() or digest(pck) != digest(source / (name + ".pck")):
        fail("Built game PCK differs from the verified source")
    privacy(app / "PrivacyInfo.xcprivacy")
    if digest(app / "PrivacyInfo.xcprivacy") != digest(source / "PrivacyInfo.xcprivacy"):
        fail("Built privacy manifest changed")
    main = app / str(info.get("CFBundleExecutable", ""))
    arches = architectures(main)
    if (device and arches != ["arm64"]) or (not device and any(a not in ("arm64", "x86_64") for a in arches)):
        fail("Built executable architecture mismatch")
    return {"projectId": project, "appId": app_id, "version": "1.0.0", "build": 13, "sdk": sdk,
            "architectures": arches, "pckSha256": digest(pck), "requiredReasonsVerified": True,
            "macBuildPerformed": True, "deviceBuild": device, "storeUploadPerformed": False}


def permitted(value, allowed):
    if isinstance(value, bool):
        return type(allowed) is bool and value == allowed
    if isinstance(value, str):
        return isinstance(allowed, str) and fnmatch.fnmatchcase(value, allowed)
    if isinstance(value, list):
        return isinstance(allowed, list) and all(any(permitted(v, a) for a in allowed) for v in value)
    if isinstance(value, dict):
        return isinstance(allowed, dict) and all(k in allowed and permitted(v, allowed[k]) for k, v in value.items())
    return value == allowed


def inspect_ipa(ipa, source, project, supplied_profile):
    app_id, _ = identity(project)
    team = os.environ.get("APPLE_TEAM_ID", "")
    expected, details = inspect_profile(supplied_profile, app_id, team)
    with tempfile.TemporaryDirectory(prefix="godot-ipa-check-", dir=os.environ["RUNNER_TEMP"]) as temporary:
        folder = pathlib.Path(temporary)
        extract_zip(ipa, folder, ipa=True)
        apps = list((folder / "Payload").glob("*.app"))
        if len(apps) != 1:
            fail("Expected one signed device App")
        app = apps[0]
        run(["codesign", "--verify", "--deep", "--strict", "-R=anchor apple generic", app])
        report = inspect_app(app, source, project, True)
        embedded, embedded_details = inspect_profile(app / "embedded.mobileprovision", app_id, team)
        if embedded_details != details:
            fail("IPA did not embed the supplied per-App profile")
        entitlements = plistlib.loads(run(["codesign", "-d", "--entitlements", ":-", app]))
        if (entitlements.get("application-identifier") != details["prefix"] + "." + app_id
                or entitlements.get("com.apple.developer.team-identifier") != team
                or entitlements.get("get-task-allow") is not False):
            fail("Signed entitlements mismatch")
        if not all(k in expected["Entitlements"] and permitted(v, expected["Entitlements"][k]) for k, v in entitlements.items()):
            fail("Signed entitlements exceed the supplied profile")
        run(["codesign", "-d", "--extract-certificates=" + str(folder / "cert"), app])
        certificate = folder / "cert0"
        if hashlib.sha256(certificate.read_bytes()).hexdigest() != details["certificateSha256"]:
            fail("IPA signer differs from this profile's certificate")
        run(["openssl", "x509", "-inform", "DER", "-in", certificate, "-checkend", "0", "-noout"])
        report.update(signatureVerified=True, profileVerified=True, signerSha256=details["certificateSha256"],
                      ipaSha256=digest(ipa), ipaBytes=ipa.stat().st_size, appStoreApproved=False)
        return report


def configure_pbx(path, project, profile_path, keychain):
    app_id, _ = identity(project)
    profile = json.loads(profile_path.read_text())
    with tempfile.TemporaryDirectory(prefix="godot-pbx-", dir=os.environ["RUNNER_TEMP"]) as temporary:
        decoded = pathlib.Path(temporary) / "project.json"
        run(["plutil", "-convert", "json", "-o", decoded, path])
        data = json.loads(decoded.read_text())
        objects = data["objects"]
        targets = [v for v in objects.values() if isinstance(v, dict) and v.get("isa") == "PBXNativeTarget" and v.get("productType") == "com.apple.product-type.application"]
        if len(targets) != 1:
            fail("Expected one Godot App target")
        configurations = objects[targets[0]["buildConfigurationList"]]["buildConfigurations"]
        for ref in configurations:
            settings = objects[ref]["buildSettings"]
            if settings.get("PRODUCT_BUNDLE_IDENTIFIER") != app_id:
                fail("App target identity mismatch")
            settings.update(CODE_SIGN_STYLE="Manual", DEVELOPMENT_TEAM=os.environ["APPLE_TEAM_ID"],
                            CODE_SIGN_IDENTITY=profile["certificateSha1"], PROVISIONING_PROFILE=profile["uuid"],
                            PROVISIONING_PROFILE_SPECIFIER=profile["name"], OTHER_CODE_SIGN_FLAGS="--keychain " + str(keychain))
        decoded.write_text(json.dumps(data))
        run(["plutil", "-convert", "xml1", "-o", path, decoded])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["source", "app", "profile", "ipa", "configure"])
    parser.add_argument("--project", choices=PROJECTS, required=True)
    parser.add_argument("--root", type=pathlib.Path)
    parser.add_argument("--zip", type=pathlib.Path)
    parser.add_argument("--metadata", type=pathlib.Path)
    parser.add_argument("--app", type=pathlib.Path)
    parser.add_argument("--ipa", type=pathlib.Path)
    parser.add_argument("--profile", type=pathlib.Path)
    parser.add_argument("--profile-details", type=pathlib.Path)
    parser.add_argument("--keychain", type=pathlib.Path)
    parser.add_argument("--device", action="store_true")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    if args.phase == "source":
        result = verify_zip(args.zip, args.metadata, args.project, args.root) if args.zip else verify_source(args.root, args.metadata, args.project)
    elif args.phase == "profile":
        _, result = inspect_profile(args.profile, identity(args.project)[0], os.environ.get("APPLE_TEAM_ID", ""))
    elif args.phase == "app":
        result = inspect_app(args.app, args.root, args.project, args.device)
    elif args.phase == "ipa":
        result = inspect_ipa(args.ipa, args.root, args.project, args.profile)
    else:
        configure_pbx(args.root / (identity(args.project)[1] + ".xcodeproj/project.pbxproj"), args.project, args.profile_details, args.keychain)
        result = {"appTargetManualSigningConfigured": True}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.phase not in ("profile", "configure"):
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.TimeoutExpired, zipfile.BadZipFile):
        raise SystemExit("Godot iOS verification stopped; private output withheld") from None
