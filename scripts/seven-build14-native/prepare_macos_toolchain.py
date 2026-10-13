"""Move the verified Godot template to macOS bundle-adjacent portable mode.

The source installer places _sc_/editor_data next to Contents/MacOS/Godot.
For a macOS .app editor, Godot 4.7 expects them next to the .app bundle.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    if sys.platform != "darwin" or len(sys.argv) != 3:
        raise SystemExit("Usage on macOS: prepare_macos_toolchain.py toolchain.json output.json")
    report_path, output = (Path(value).resolve() for value in sys.argv[1:3])
    owned = (Path(os.environ["RUNNER_TEMP"]) / "seven-build14-toolchain").resolve()
    if not report_path.is_relative_to(owned) or report_path != owned / "toolchain.json":
        raise SystemExit("Only this job's verified toolchain report may be used")
    tool = json.loads(report_path.read_text(encoding="utf-8"))
    godot = Path(tool.get("godot", "")).resolve()
    if (not godot.is_file() or not godot.is_relative_to(owned)
            or godot.name != "Godot" or godot.parent.name != "MacOS"
            or godot.parents[1].name != "Contents" or godot.parents[2].name != "Godot.app"
            or tool.get("godotVersion") != "4.7.2"
            or tool.get("publisherDigestsVerified") is not True):
        raise SystemExit("Official Godot 4.7.2 macOS app layout differs")
    bundle = godot.parents[2]
    portable = bundle.parent
    internal = godot.parent
    internal_marker = internal / "_sc_"
    internal_data = internal / "editor_data"
    external_marker = portable / "_sc_"
    external_data = portable / "editor_data"
    template = internal_data / "export_templates/4.7.2.stable/ios.zip"
    if (not internal_marker.is_file() or not template.is_file()
            or external_marker.exists() or external_data.exists()
            or internal_marker.is_symlink() or internal_data.is_symlink()
            or not internal_data.resolve().is_relative_to(owned)):
        raise SystemExit("Fresh bundle-adjacent portable layout required")
    before = sha(template)
    internal_marker.unlink()
    internal_data.rename(external_data)
    external_marker.write_text("", encoding="utf-8")
    relocated = external_data / "export_templates/4.7.2.stable/ios.zip"
    if not external_marker.is_file() or not relocated.is_file() or sha(relocated) != before:
        raise SystemExit("Relocated official iOS template hash differs")
    version = subprocess.run([str(godot), "--version"], capture_output=True, text=True, timeout=60)
    if version.returncode or not version.stdout.startswith("4.7.2.stable.official."):
        raise SystemExit("Relocated official Godot editor did not execute")
    result = {"schemaVersion": 1, "engineVersion": "4.7.2", "officialEditorExecuted": True,
              "publisherDigestsVerified": True, "selfContainedMarker": "beside-Godot.app",
              "editorData": "beside-Godot.app", "iosTemplatePresent": True,
              "iosTemplateSha256": before, "storeUploadPerformed": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
