"""Package exact-source Seven build 13 Simulator gameplay evidence, never publish to Apple.

The only network write is a one-shot upload of a bounded evidence ZIP to the
pre-existing draft GitHub Release. An uncertain upload result must be read back,
not replayed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import struct
import subprocess
import sys
import zipfile

REPO = "mars-tw/taiwan-train-math"
TAG = "seven-build13-ios-qa-20261013"
RELEASE_ID = 411789919
SOURCE_COMMIT = "b9377588c91b95bba81e98c343e51886f3d38b01"
SOURCE_PIN = "b975e22cae4e7f7259e76b5b71e3dce5400a5739e6599a428b09d20015d81e1b"
PCK_SHA256 = "adb2466826ce250b8b357b706b3520c9e69792a2fceb06da5bbd3f724a9f9439"
SIGNED_RUN_ID = 38417996013
SIGNED_IPA_SHA256 = "75d348b547cc128643f8a2c7235dc28d55756cb5c087654cbd919e61450c16c8"
SIGNED_EVIDENCE_SHA256 = "500e29b06681bdd071d8c423c70f19d8ee35402fc7fecea56585f03105db8887"
SIGNED_EVIDENCE_ASSET_ID = 637418576
VERIFIER_SHA256 = "4aefa929be7e149e6006f068fd32fa8b1832f5fab42ac66129ab92bc59a95eb0"
MODELS = {"iphone": "iPhone 17 Pro", "ipad": "iPad Pro 13-inch (M4)"}
SIZES = {"iphone": (2622, 1206), "ipad": (2752, 2064)}


def fail(message: str) -> None:
    raise ValueError(message)


def sha(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def obj(path: pathlib.Path) -> dict:
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= 1024 * 1024:
        fail("Missing or unsafe gameplay JSON")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("Invalid gameplay JSON object")
    return value


def png(path: pathlib.Path, expected: tuple[int, int], *, opaque: bool) -> dict:
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= 24 * 1024**2:
        fail("Missing or unsafe native PNG")
    with path.open("rb") as stream:
        head = stream.read(26)
    if len(head) != 26 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        fail("Native screenshot is not PNG")
    size = struct.unpack(">II", head[16:24])
    if size != expected or head[24] != 8 or (opaque and head[25] != 2):
        fail("Native landscape screenshot size or RGB color type differs")
    return {"width": size[0], "height": size[1], "bytes": path.stat().st_size, "sha256": sha(path)}


def diagnostic_png(path: pathlib.Path) -> dict:
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= 24 * 1024**2:
        fail("Missing or unsafe native diagnostic PNG")
    with path.open("rb") as stream:
        head = stream.read(26)
    if (len(head) != 26 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR"
            or head[24] not in (1, 2, 4, 8, 16)):
        fail("Diagnostic frame is not a bounded PNG")
    width, height = struct.unpack(">II", head[16:24])
    if not 0 < width <= 4096 or not 0 < height <= 4096:
        fail("Unbounded diagnostic screenshot geometry")
    return {"width": width, "height": height, "bytes": path.stat().st_size, "sha256": sha(path)}


def safe_file(root: pathlib.Path, name: str) -> pathlib.Path:
    if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9._/-]{1,150}", name)
            or name.startswith("/") or any(part in ("", ".", "..") for part in name.split("/"))):
        fail("Unsafe evidence path")
    path = root.joinpath(*name.split("/"))
    if not path.is_file() or path.is_symlink():
        fail("Missing or linked evidence file")
    return path


def check_inputs(stage: pathlib.Path, tool_commit: str) -> dict:
    if sha(stage / "SHA256SUMS") != SOURCE_PIN:
        fail("Original source manifest differs")
    metadata = obj(stage / "seven-district-reckoning-build13-source-verification.json")
    if (metadata.get("sourceCommit"), metadata.get("sourceFiles"), metadata.get("nativeBuild"),
            metadata.get("pckSha256")) != (SOURCE_COMMIT, 47, 13, PCK_SHA256):
        fail("Original source identity differs")
    p = obj(stage / "gameplay-provenance.json")
    if (p.get("repository"), p.get("releaseTag"), p.get("releaseId"),
            p.get("sourceCommit"), p.get("sourcePin"), p.get("signedRunId"),
            p.get("signedIpaSha256"), p.get("signedEvidenceSha256"),
            p.get("signedEvidenceAssetId"), p.get("captureToolsCommit"),
            p.get("appleSecretsUsed"), p.get("storeUploadPerformed")) != (
                REPO, TAG, RELEASE_ID, SOURCE_COMMIT, SOURCE_PIN, SIGNED_RUN_ID,
                SIGNED_IPA_SHA256, SIGNED_EVIDENCE_SHA256, SIGNED_EVIDENCE_ASSET_ID,
                tool_commit, False, False):
        fail("Exact source/signed IPA/gameplay tool provenance differs")
    tools = p.get("captureToolSha256")
    if (not isinstance(tools, dict) or set(tools) != {
            "scripts/ci_seven_build13_gameplay_capture.sh",
            "scripts/ci_seven_build13_gameplay_package.py",
            "scripts/seven_build13_gameplay_probe/run_probe.sh",
            "scripts/seven_build13_gameplay_probe/SevenProbe.xcodeproj/project.pbxproj",
            "scripts/seven_build13_gameplay_probe/SevenProbe.xcodeproj/xcshareddata/xcschemes/SevenProbe.xcscheme",
            "scripts/seven_build13_gameplay_probe/SevenProbeHost/AppDelegate.swift",
            "scripts/seven_build13_gameplay_probe/SevenDistrictUITests/SevenDistrictUITests.swift",
            "scripts/ci_verify_seven_build13.py"}
            or tools["scripts/ci_verify_seven_build13.py"] != VERIFIER_SHA256
            or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in tools.values())):
        fail("Exact gameplay tool hash set differs")
    return p


def collect(stage: pathlib.Path, output: pathlib.Path, commit: str, outcome: str) -> tuple[dict, dict[str, pathlib.Path]]:
    if outcome not in ("success", "failure"):
        fail("Explicit capture outcome required")
    provenance = check_inputs(stage, commit)
    source = obj(output / "source-verification.json")
    if (source.get("projectId"), source.get("build"), source.get("sourceFiles"),
            source.get("pckSha256"), source.get("sourceVerified")) != (
                "seven-district-reckoning", 13, 47, PCK_SHA256, True):
        fail("Extracted source verification differs")
    game = output / "gameplay"
    files = {
        "source-verification.json": output / "source-verification.json",
        "source-metadata.json": stage / "seven-district-reckoning-build13-source-verification.json",
        "gameplay-provenance.json": stage / "gameplay-provenance.json",
    }
    for name in ("simulator-architecture.json", "simulator-verification.json", "sim-build-failure.json",
                 "gameplay-capture.json", "gameplay-failure.json"):
        path = game / name
        if path.is_file() and not path.is_symlink():
            files["gameplay/" + name] = path
    captures: list[dict] = []
    if outcome == "success":
        receipt = obj(game / "gameplay-capture.json")
        if (receipt.get("projectId"), receipt.get("version"), receipt.get("build"),
                receipt.get("sourcePckSha256"), receipt.get("actualSimulator"),
                receipt.get("visualReviewPending"), receipt.get("listingUploadReady"),
                receipt.get("appleSecretsUsed"), receipt.get("storeUploadPerformed")) != (
                    "seven-district-reckoning", "1.0.0", 13, PCK_SHA256,
                    True, True, False, False, False):
            fail("Gameplay receipt identity or review boundary differs")
        rows = receipt.get("captures")
        if not isinstance(rows, list) or len(rows) != 2 or {row.get("kind") for row in rows if isinstance(row, dict)} != set(MODELS):
            fail("Exactly two real device-size gameplay captures required")
        for row in rows:
            kind = row["kind"]
            if (row.get("model") != MODELS[kind] and
                    not (kind == "ipad" and str(row.get("model", "")).startswith(MODELS[kind]))):
                fail("Actual required Simulator model differs")
            if (row.get("orientation") != ("landscapeLeft" if kind == "iphone" else "landscapeRight")
                    or row.get("startTappedByXCUITest") is not True
                    or row.get("main001VerifiedByXCUITest") is not True
                    or row.get("nativeResolution") is not True
                    or row.get("cropApplied") is not False
                    or row.get("syntheticContentAdded") is not False):
                fail("Gameplay interaction or native-frame provenance differs")
            activation_name = f"raw/{kind}-activation.png"
            title_name = f"raw/{kind}-title.png"
            game_name = f"raw/{kind}-main001.png"
            candidate_name = f"candidates/{kind}-main001.png"
            if (row.get("activationRaw") != activation_name
                    or row.get("titleRaw") != title_name or row.get("gameplayRaw") != game_name
                    or row.get("listingCandidate") != candidate_name):
                fail("Exact activation/title/gameplay screenshot names required")
            phase_sources = row.get("phaseSources")
            if not isinstance(phase_sources, dict) or set(phase_sources) != {"activation", "title", "main001"}:
                fail("Exact dual-original phase source set required")
            for phase, label in (("activated", "activation"), ("title", "title"), ("main001", "main001")):
                item = phase_sources[label]
                chosen = item.get("chosenSource") if isinstance(item, dict) else None
                if chosen not in ("simctl", "xctest") or set(item) != {"chosenSource", "simctl", "xctest"}:
                    fail("Selected original source missing")
                selection_name = f"{kind}-{label}-source-selection.json"
                selection = obj(game / selection_name)
                if (selection.get("phase"), selection.get("chosenSource"),
                        selection.get("requiredWidth"), selection.get("requiredHeight"),
                        selection.get("noRotateCropOrComposite")) != (
                        phase, chosen, SIZES[kind][0], SIZES[kind][1], True):
                    fail("Native dual-source selection receipt differs")
                files["gameplay/" + selection_name] = game / selection_name
                gate = None
                for method, source in (("simctl", "xcrun simctl io <UDID> screenshot --type=png"),
                                       ("xctest", "XCUIScreen.main.screenshot().pngRepresentation")):
                    original = item[method]
                    name = f"raw/{kind}-{label}-{method}.png"
                    evidence_name = f"{kind}-{label}-{method}-evidence.json"
                    evidence = obj(game / evidence_name)
                    if not isinstance(original, dict) or original.get("file") != name or original.get("source") != source:
                        fail("Original source path or method differs")
                    path = safe_file(game, name)
                    frame = diagnostic_png(path)
                    if (original.get("sha256"), original.get("width"), original.get("height"), original.get("bytes")) != (
                            frame["sha256"], frame["width"], frame["height"], frame["bytes"]):
                        fail("Original source hash/geometry differs")
                    if (evidence.get("source"), evidence.get("sha256"), evidence.get("width"),
                            evidence.get("height"), evidence.get("bytes"), evidence.get("nativeGeometryAccepted")) != (
                            source, frame["sha256"], frame["width"], frame["height"], frame["bytes"],
                            (frame["width"], frame["height"]) == SIZES[kind]):
                        fail("Original source evidence differs")
                    if method == "xctest":
                        gate_text = evidence.get("uiTestGate", "")
                        if (f"xctestPNGFile=seven-{phase}-xctest.png" not in gate_text
                                or f"xctestPNGBytes={frame['bytes']}" not in gate_text
                                or f"xctestPNGSHA256={frame['sha256']}" not in gate_text
                                or f"xctestPNGIHDRPixels={frame['width']},{frame['height']}" not in gate_text):
                            fail("XCTest PNG differs from its atomic ready marker")
                    selected = selection.get(method, {})
                    if (selected.get("sha256"), selected.get("width"), selected.get("height"),
                            selected.get("bytes")) != (
                            frame["sha256"], frame["width"], frame["height"], frame["bytes"]):
                        fail("Dual-source selection hash/geometry differs")
                    if method == chosen:
                        if (frame["width"], frame["height"]) != SIZES[kind]:
                            fail("Chosen original is not native landscape")
                        gate = evidence.get("uiTestGate", "")
                    files["gameplay/" + name] = path
                    files["gameplay/" + evidence_name] = game / evidence_name
                if not isinstance(gate, str) or (label == "activation" and "phase=activated" not in gate) \
                        or (label == "title" and ("phase=title" not in gate or "startOCRBox=" not in gate)) \
                        or (label == "main001" and "mission=MAIN-001" not in gate):
                    fail("XCUITest activation/title/MAIN-001 gate differs")
            for name, opaque, hash_field in ((activation_name, False, "activationRawSha256"),
                                             (title_name, False, "titleRawSha256"),
                                             (game_name, False, "gameplayRawSha256"),
                                             (candidate_name, True, "listingCandidateSha256")):
                path = safe_file(game, name)
                frame = png(path, SIZES[kind], opaque=opaque)
                if row.get(hash_field) != frame["sha256"]:
                    fail("Screenshot hash in gameplay receipt differs")
                if name != candidate_name:
                    label = "activation" if name == activation_name else "title" if name == title_name else "main001"
                    chosen = phase_sources[label]["chosenSource"]
                    if frame["sha256"] != phase_sources[label][chosen]["sha256"]:
                        fail("Selected native frame differs from its original bytes")
                files["gameplay/" + name] = path
            captures.append(row)
    else:
        failure_path = game / "gameplay-failure.json"
        if not failure_path.exists():
            game.mkdir(parents=True, exist_ok=True)
            failure_path.write_text(json.dumps({"projectId": "seven-district-reckoning",
                "phase": "gameplay-capture", "failureCode": "CAPTURE_STEP_FAILED_WITHOUT_DETAIL",
                "rawLogsPublished": False, "appleSecretsUsed": False,
                "storeUploadPerformed": False}, indent=2) + "\n", encoding="utf-8")
            files["gameplay/gameplay-failure.json"] = failure_path
        failure = obj(failure_path)
        if (failure.get("projectId"), failure.get("phase"), failure.get("rawLogsPublished"),
                failure.get("appleSecretsUsed"), failure.get("storeUploadPerformed")) != (
                    "seven-district-reckoning", "gameplay-capture", False, False, False):
            fail("Bounded gameplay failure receipt differs")
        if not re.fullmatch(r"[A-Z0-9_]{3,80}", str(failure.get("failureCode", ""))):
            fail("Unsafe gameplay failure code")
        diagnostics = failure.get("diagnostics", [])
        if (not isinstance(diagnostics, list) or len(diagnostics) > 20
                or any(not isinstance(line, str) or len(line) > 500 for line in diagnostics)):
            fail("Unsafe bounded gameplay diagnostics")
        exits = failure.get("probeExitReceipts", [])
        if (not isinstance(exits, list) or len(exits) > 2
                or any(not isinstance(row, dict) or row.get("kind") not in MODELS
                       or not isinstance(row.get("phase"), str) or len(row["phase"]) > 80
                       for row in exits)):
            fail("Unsafe probe exit receipt")
        selections = failure.get("dualSourceSelections", [])
        if (not isinstance(selections, list) or len(selections) > 6
                or len({(row.get("kind"), row.get("phase")) for row in selections if isinstance(row, dict)}) != len(selections)):
            fail("Unsafe dual-source failure selection list")
        for item in selections:
            if (not isinstance(item, dict) or item.get("kind") not in MODELS
                    or item.get("phase") not in ("activated", "title", "main001")
                    or (item.get("requiredWidth"), item.get("requiredHeight")) != SIZES[item["kind"]]
                    or item.get("chosenSource") not in (None, "simctl", "xctest")
                    or item.get("noRotateCropOrComposite") is not True):
                fail("Unsafe dual-source failure geometry receipt")
            for method in ("simctl", "xctest"):
                row = item.get(method)
                if (not isinstance(row, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", "")))
                        or not isinstance(row.get("width"), int) or not 0 < row["width"] <= 4096
                        or not isinstance(row.get("height"), int) or not 0 < row["height"] <= 4096):
                    fail("Unsafe original PNG dimension/hash receipt")
        partial = failure.get("partialScreenshots", [])
        if (not isinstance(partial, list) or len(partial) > 16
                or len({row.get("file") for row in partial if isinstance(row, dict)}) != len(partial)):
            fail("Unsafe partial gameplay screenshot list")
        for row in partial:
            if not isinstance(row, dict):
                fail("Invalid partial gameplay screenshot record")
            name = row.get("file", "")
            match = re.fullmatch(r"partial/(iphone|ipad)-(activation-xctest|activation-simctl|activation-failure|title-wait-t120|title-wait-t240|title-wait-t360|title-wait-final|title-xctest|title-simctl|main001-xctest|main001-simctl)\.png", name)
            if not match:
                fail("Unexpected partial screenshot name")
            path = safe_file(game, name)
            frame = diagnostic_png(path)
            if (row.get("bytes"), row.get("sha256"), row.get("width"), row.get("height")) != (
                    frame["bytes"], frame["sha256"], frame["width"], frame["height"]) \
                    or row.get("listingCandidate") is not False:
                fail("Partial native screenshot hash or geometry differs")
            files["gameplay/" + name] = path
        partial_by_name = {row["file"]: row for row in partial}
        for item in selections:
            label = "activation" if item["phase"] == "activated" else item["phase"]
            for method in ("simctl", "xctest"):
                row = partial_by_name.get(f"partial/{item['kind']}-{label}-{method}.png")
                if row is None:
                    fail("Dual-source selection lacks a retained original PNG")
                if (row["sha256"], row["width"], row["height"]) != (
                        item[method]["sha256"], item[method]["width"], item[method]["height"]):
                    fail("Retained original differs from dual-source failure selection")
    if len(files) > 56 or sum(p.stat().st_size for p in files.values()) > 320 * 1024**2:
        fail("Gameplay evidence exceeds bound")
    manifest = {"repository": REPO, "releaseTag": TAG, "releaseId": RELEASE_ID,
                "releaseDraft": True, "projectId": "seven-district-reckoning", "version": "1.0.0",
                "build": 13, "sourceCommit": SOURCE_COMMIT, "sourcePin": SOURCE_PIN,
                "pckSha256": PCK_SHA256, "signedRunId": SIGNED_RUN_ID,
                "signedIpaSha256": SIGNED_IPA_SHA256,
                "signedEvidenceSha256": SIGNED_EVIDENCE_SHA256,
                "signedEvidenceAssetId": SIGNED_EVIDENCE_ASSET_ID,
                "captureToolsCommit": commit, "captureToolSha256": provenance["captureToolSha256"],
                "captureStepOutcome": outcome,
                "status": "MAIN001_CANDIDATES_VISUAL_REVIEW_PENDING" if outcome == "success" else "GAMEPLAY_CAPTURE_FAILED_EVIDENCE",
                "captures": captures, "listingUploadReady": False, "visualReviewPending": True,
                "appleSecretsUsed": False, "storeUploadPerformed": False}
    return manifest, files


def release() -> dict:
    result = subprocess.run(["gh", "api", "--method", "GET", f"repos/{REPO}/releases/{RELEASE_ID}"],
                            capture_output=True, timeout=60)
    if result.returncode:
        fail("Draft Release read failed; raw output withheld")
    value = json.loads(result.stdout)
    if (value.get("id"), value.get("tag_name"), value.get("draft")) != (RELEASE_ID, TAG, True):
        fail("Original draft Release identity/state differs")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--capture-outcome", choices=("success", "failure"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[1-9][0-9]*", args.run_id) or not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        fail("Exact run and tools commit required")
    stage, output = args.input.resolve(), args.output.resolve()
    manifest, files = collect(stage, output, args.commit, args.capture_outcome)
    manifest["runId"] = args.run_id
    manifest["entries"] = [{"name": name, "bytes": path.stat().st_size, "sha256": sha(path)}
                           for name, path in sorted(files.items())]
    manifest_path = output / "gameplay-payload-manifest.json"
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    files[manifest_path.name] = manifest_path
    archive = output / f"seven-build13-gameplay-{args.run_id}.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
        for name, path in sorted(files.items()):
            z.write(path, name)
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist()) != len(files) or set(z.namelist()) != set(files) or z.testzip() is not None:
            fail("Evidence archive members or CRC differ")
        for name, path in files.items():
            if z.getinfo(name).file_size != path.stat().st_size or hashlib.sha256(z.read(name)).hexdigest() != sha(path):
                fail("Evidence archive member differs")
    receipt = {"status": manifest["status"], "asset": archive.name,
               "bytes": archive.stat().st_size, "sha256": sha(archive),
               "listingUploadReady": False, "storeUploadPerformed": False}
    if not args.upload:
        print(json.dumps({**receipt, "uploadPerformed": False}, indent=2))
        return
    if (os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_REF"),
            os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_SHA")) != (
                REPO, "refs/heads/main", args.run_id, args.commit) or not os.environ.get("GH_TOKEN"):
        fail("Only the exact trusted main run may upload evidence")
    before = release()
    if archive.name in {item.get("name") for item in before.get("assets", [])}:
        fail("Exact-run gameplay evidence asset already exists")
    journal = output / "gameplay-upload-once.json"
    with journal.open("x", encoding="utf-8") as stream:
        json.dump({"releaseId": RELEASE_ID, "runId": args.run_id, "attempt": "ONE_SHOT",
                   "asset": archive.name, "bytes": archive.stat().st_size,
                   "sha256": receipt["sha256"]}, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    result = subprocess.run(["gh", "release", "upload", TAG, str(archive), "--repo", REPO],
                            capture_output=True, timeout=900)
    if result.returncode:
        fail("Gameplay evidence upload failed or uncertain; inspect draft before retry")
    after = release()
    remote = next((item for item in after.get("assets", []) if item.get("name") == archive.name), None)
    if (not remote or remote.get("state") != "uploaded" or remote.get("size") != archive.stat().st_size
            or remote.get("digest") != "sha256:" + receipt["sha256"]):
        fail("Gameplay evidence readback incomplete; inspect draft before retry")
    print(json.dumps({**receipt, "uploadPerformed": True}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError,
            subprocess.TimeoutExpired, zipfile.BadZipFile) as error:
        sys.exit(f"Seven gameplay package stopped: {error}")
