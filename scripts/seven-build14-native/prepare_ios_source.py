"""Bind a fresh Godot iOS export to the reviewed Seven build 14 Git source."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys

SOURCE_SHA = "a5cc913f566189d13ecf39b4229848fec8a43df1"
APP_ID = "tw.mars.sevendistrictreckoning"
BUILD = 14


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def main() -> None:
    source, out = (Path(value).resolve() for value in sys.argv[1:3])
    if len(sys.argv) != 3 or git(source, "rev-parse", "HEAD") != SOURCE_SHA:
        raise SystemExit("Exact Seven build 14 source commit required")
    config = json.loads((source / "native/build-config.json").read_text(encoding="utf-8"))
    if (config.get("appId"), config.get("nativeVersion"), config.get("nativeBuild"), config.get("engineVersion")) != (APP_ID, "1.0.0", BUILD, "4.7.2"):
        raise SystemExit("Native config identity differs")
    presets = (source / "godot/export_presets.cfg").read_text(encoding="utf-8")
    if presets.count("version/code=14") != 2 or presets.count('application/version="14"') != 1:
        raise SystemExit("Android/iOS preset build numbers differ")
    status = git(source, "status", "--porcelain", "-uall").splitlines()
    if any(not line.startswith(" M godot/") or not line.endswith(".import") for line in status):
        raise SystemExit("Only Godot-generated import records may differ from the pinned checkout")
    export = json.loads((source / "deliverables/native/ios-verification.json").read_text(encoding="utf-8"))
    if (export.get("sourceSha"), export.get("appId"), export.get("nativeBuild"), export.get("status"), export.get("signed"), export.get("uploaded")) != (SOURCE_SHA, APP_ID, BUILD, "ios-xcode-source-created-not-compiled", False, False):
        raise SystemExit("Godot source-only export receipt differs")
    root = source / "deliverables/native/ios"
    if root.is_symlink() or not root.is_dir() or any(path.is_symlink() for path in root.rglob("*")):
        raise SystemExit("Linked iOS source path is disallowed")
    files = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda p: p.relative_to(root).as_posix())
    if len(files) != 47:
        raise SystemExit("Expected 47 original Godot iOS source files")
    records = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)} for path in files]
    pck = root / "SevenDistrict.pck"
    if pck.read_bytes()[:4] != b"GDPC":
        raise SystemExit("Godot game PCK header missing")
    pbx = (root / "SevenDistrict.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
    if (set(re.findall(r"PRODUCT_BUNDLE_IDENTIFIER\s*=\s*([^;]+);", pbx)) != {APP_ID}
            or set(re.findall(r"MARKETING_VERSION\s*=\s*([^;]+);", pbx)) != {"1.0.0"}
            or set(re.findall(r"CURRENT_PROJECT_VERSION\s*=\s*([^;]+);", pbx)) != {"14"}):
        raise SystemExit("Xcode identity/version differs")
    privacy = plistlib.loads((root / "PrivacyInfo.xcprivacy").read_bytes())
    if privacy.get("NSPrivacyTracking") is not False:
        raise SystemExit("Privacy tracking declaration differs")
    out.mkdir(parents=True, exist_ok=True)
    metadata = {"appId": APP_ID, "nativeVersion": "1.0.0", "nativeBuild": BUILD,
        "engineVersion": "4.7.2", "sourceVersion": config["sourceVersion"],
        "sourceCommit": SOURCE_SHA, "sourceCheckoutHead": SOURCE_SHA,
        "committedGameSourceMatches": True, "sourceWorkingTreeDirtyAfterExport": bool(status),
        "workingTreeDifferencesAfterExport": "Generated Godot import records only" if status else "None",
        "status": "unsigned-xcode-source-not-mac-compiled", "signed": False,
        "storeUploadPerformed": False, "sourceFiles": len(files),
        "project": "SevenDistrict.xcodeproj", "scheme": "SevenDistrict",
        "isolatedPresetSha256": sha(source / "godot/export_presets.cfg"),
        "pckSha256": sha(pck), "pckBytes": pck.stat().st_size, "files": records}
    target = out / "ios-source-metadata.json"
    target.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as env:
        env.write("SEVEN_BUILD14_PCK_SHA256=" + metadata["pckSha256"] + "\n")
    print(json.dumps({"sourceSha": SOURCE_SHA, "build": BUILD, "sourceFiles": len(files),
                      "pckSha256": metadata["pckSha256"], "metadataSha256": sha(target)}))


if __name__ == "__main__":
    main()
