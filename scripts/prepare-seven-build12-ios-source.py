"""Stage the reviewed Seven District build 12 export for a draft Release.

This writes only unsigned public inputs. It never reads signing secrets or calls GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import plistlib
import re
import shutil
import subprocess
import sys
import zipfile

SOURCE_COMMIT = "f6fc1155b0296f74972775a0426af25af4e04416"
GAME_BASE_COMMIT = "905e123c4c0ed632a665f857e438f32ada590cc9"
PCK_SHA256 = "d4c19f09bd7f06c038c61ded32d3f79c5ef9f13042fb1f35b951a88443fc5bc8"
ZIP_NAME = "SevenDistrict-1.0.0-build12-unsigned-source.zip"
METADATA_NAME = "seven-district-reckoning-build12-source-verification.json"
HELPERS = ("ci_verify_seven_build12.py", "ci_seven_ios_build12_export.sh",
           "ci_seven_build12_evidence.py")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(root: pathlib.Path, *args: str) -> str:
    process = subprocess.run(["git", "-c", "core.safecrlf=false", *args], cwd=root,
                             capture_output=True, text=True, timeout=120)
    if process.returncode:
        raise ValueError("Could not verify the local game commit")
    return process.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=pathlib.Path,
                        help="Isolated Seven District checkout with deliverables/native/ios")
    parser.add_argument("--output", required=True, type=pathlib.Path,
                        help="New, empty local staging directory outside Git")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    ios = source / "deliverables/native/ios"
    checkout_head = git(source, "rev-parse", "HEAD")
    if checkout_head != SOURCE_COMMIT or git(source, "merge-base", "HEAD", GAME_BASE_COMMIT) != GAME_BASE_COMMIT:
        raise ValueError("The source checkout is not the reviewed clean merge commit")
    committed_after_base = git(source, "diff", "--name-only", GAME_BASE_COMMIT, "HEAD").splitlines()
    permitted_native = {"godot/export_presets.cfg", "native/build-config.json",
                        "tools/export_mobile.py", "tools/install_native_toolchain.py"}
    if set(committed_after_base) - permitted_native:
        raise ValueError("A commit changed game files after the reviewed game commit")
    changed = git(source, "diff", "--name-only", "HEAD", "--", "godot").splitlines()
    meaningful = [name for name in changed
                  if not name.endswith(".import")]
    untracked_game = git(source, "ls-files", "--others", "--exclude-standard", "--",
                         "godot/scripts", "godot/scenes", "godot/data", "godot/assets",
                         "godot/project.godot").splitlines()
    if meaningful or untracked_game:
        raise ValueError("Isolated game source differs from the reviewed commit")
    config = json.loads((source / "native/build-config.json").read_text(encoding="utf-8"))
    if (config.get("appId"), config.get("nativeVersion"), config.get("nativeBuild"),
        config.get("engineVersion")) != (
            "tw.mars.sevendistrictreckoning", "1.0.0", 12, "4.7.2"):
        raise ValueError("Committed native build config is not build 12")
    preset = (source / "godot/export_presets.cfg").read_text(encoding="utf-8")
    if not re.search(r'application/version="12"', preset) or not re.search(
            r'application/bundle_identifier="tw\.mars\.sevendistrictreckoning"', preset):
        raise ValueError("Native export preset identity/build mismatch")
    if not ios.is_dir() or ios.is_symlink():
        raise ValueError("Missing isolated Xcode export")
    paths = sorted((path for path in ios.rglob("*") if path.is_file()),
                   key=lambda path: path.relative_to(ios).as_posix())
    if len(paths) != 47 or any(path.is_symlink() for path in ios.rglob("*")):
        raise ValueError("The isolated export must contain exactly 47 real files")
    if sha256(ios / "SevenDistrict.pck") != PCK_SHA256:
        raise ValueError("The exported PCK differs from the reviewed build 12")
    pbx = (ios / "SevenDistrict.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
    if (not re.search(r"CURRENT_PROJECT_VERSION\s*=\s*12;", pbx) or
        not re.search(r"MARKETING_VERSION\s*=\s*1\.0\.0;", pbx) or
        set(re.findall(r"PRODUCT_BUNDLE_IDENTIFIER\s*=\s*([^;\s]+);", pbx)) !=
            {"tw.mars.sevendistrictreckoning"}):
        raise ValueError("The exported Xcode project does not bind build 12")
    privacy = plistlib.loads((ios / "PrivacyInfo.xcprivacy").read_bytes())
    if privacy.get("NSPrivacyTracking") is not False:
        raise ValueError("Privacy declaration changed")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Staging directory must be empty; no overwrite")
    output.mkdir(parents=True, exist_ok=True)
    files = [{"path": path.relative_to(ios).as_posix(), "bytes": path.stat().st_size,
              "sha256": sha256(path)} for path in paths]
    manifest_sha = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    archive = output / ZIP_NAME
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as zipped:
        for path in paths:
            relative = path.relative_to(ios).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 10, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 << 16)
            with path.open("rb") as stream, zipped.open(info, "w", force_zip64=True) as target:
                shutil.copyfileobj(stream, target, length=1024 * 1024)
    tracked_dirty = bool(git(source, "status", "--porcelain", "--untracked-files=no"))
    metadata = {
        "appId": "tw.mars.sevendistrictreckoning", "nativeVersion": "1.0.0",
        "nativeBuild": 12, "engineVersion": "4.7.2", "sourceVersion": "0.4.0",
        "sourceCommit": SOURCE_COMMIT, "gameBaseCommit": GAME_BASE_COMMIT,
        "sourceCheckoutHead": checkout_head,
        "committedGameSourceMatches": True,
        "sourceWorkingTreeDirtyAfterExport": tracked_dirty,
        "workingTreeDifferencesAfterExport": "Generated Godot import records only" if tracked_dirty else "none",
        "status": "unsigned-xcode-source-not-mac-compiled", "signed": False,
        "storeUploadPerformed": False, "sourceFiles": 47,
        "project": "SevenDistrict.xcodeproj", "scheme": "SevenDistrict",
        "sourceInputManifestSha256": manifest_sha,
        "isolatedPresetSha256": sha256(source / "godot/export_presets.cfg"),
        "pckSha256": PCK_SHA256,
        "zip": {"file": ZIP_NAME, "bytes": archive.stat().st_size, "sha256": sha256(archive)},
        "files": files,
    }
    (output / METADATA_NAME).write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
    helper_root = pathlib.Path(__file__).resolve().parent
    for name in HELPERS:
        shutil.copyfile(helper_root / name, output / name)
    with (output / "SHA256SUMS").open("x", encoding="ascii", newline="\n") as sums:
        for name in sorted((ZIP_NAME, METADATA_NAME, *HELPERS)):
            sums.write(f"{sha256(output / name)}  {name}\n")
    print(json.dumps({"sourceCommit": SOURCE_COMMIT, "pckSha256": PCK_SHA256,
                      "sourceFiles": len(files), "sourceZipBytes": archive.stat().st_size,
                      "sourceZipSha256": metadata["zip"]["sha256"],
                      "sumsSha256": sha256(output / "SHA256SUMS")}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.TimeoutExpired, zipfile.BadZipFile) as error:
        sys.exit(f"Build 12 source staging stopped: {error}")
