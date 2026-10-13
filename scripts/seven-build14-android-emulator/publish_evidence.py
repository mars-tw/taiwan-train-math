"""Package one owned KVM QA run and append its unique ZIP to the pinned draft."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
REPO = "mars-tw/taiwan-train-math"
REF = "refs/heads/main"
RELEASE_TARGET = "cca54d495b1fc3ed7b642a1374bbed3705f8d298"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def get_release(release_id):
    result = subprocess.run(["gh", "api", f"repos/{REPO}/releases/{release_id}"], capture_output=True, timeout=45)
    if result.returncode:
        raise RuntimeError("Draft release readback failed; provider output withheld")
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fixture-output", type=Path)
    args = parser.parse_args()
    m = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    if (m.get("repository") != REPO or m.get("branch") != REF.removeprefix("refs/heads/")
            or m.get("apk", {}).get("sha256") != "bd72d2697dc91b995ba55f59d82d4b5c5764e2401f6ec48012ec910257de73e7"
            or m.get("versionCode") != 14
            or m.get("source", {}).get("sourceCommit") != "a5cc913f566189d13ecf39b4229848fec8a43df1"
            or m.get("signingReceipt", {}).get("sha256") != "e77d06696aa2452650f3cd91ebcc31613231c9053d3f1cf43060d7ae0f0a6e3e"
            or m.get("approvalManifest", {}).get("sha256") != "70fe49b8212ac707484c3f56a7b6370e96fa8ec4fb8f6e959ebb748d16c9b17e"
            or m.get("release", {}).get("draft") is not True
            or m.get("release", {}).get("releaseId") != 412073733
            or m.get("release", {}).get("tag") != "seven-build14-android-emulator-qa-20261014-bd72d269"):
        raise RuntimeError("Fixed evidence publication manifest mismatch")
    if args.dry_run:
        output = args.fixture_output.resolve() if args.fixture_output else HERE / "dry-run-output"
        output.mkdir(parents=True, exist_ok=True)
        run_id, attempt = "dryrun", "1"
        temp = HERE
        outcomes = {name: "dryrun" for name in ("fetch", "kvm", "bootstrap", "probe")}
    else:
        if (os.environ.get("GITHUB_ACTIONS") != "true"
                or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
                or os.environ.get("GITHUB_REPOSITORY") != REPO
                or os.environ.get("GITHUB_REF") != REF or os.environ.get("GH_TOKEN") is None):
            raise RuntimeError("Fixed QA runner only")
        run_id, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
        if not re.fullmatch(r"[0-9]+", run_id) or attempt != "1":
            raise RuntimeError("Only original one-shot run attempt may publish evidence")
        outcomes = {name: os.environ.get(name.upper() + "_OUTCOME", "missing")
                    for name in ("fetch", "kvm", "bootstrap", "probe")}
        if any(value not in {"success", "failure", "skipped"} for value in outcomes.values()):
            raise RuntimeError("Current-run step outcomes are incomplete")
        temp = Path(os.environ["RUNNER_TEMP"]).resolve()
        raw_workspace = Path(os.environ["GITHUB_WORKSPACE"])
        if raw_workspace.is_symlink():
            raise RuntimeError("Runner workspace is linked")
        workspace = raw_workspace.resolve()
        output_parent = workspace / "output"
        output = output_parent / "seven-build14-android-emulator"
        if output_parent.is_symlink() or output.is_symlink() or not output.is_relative_to(workspace):
            raise RuntimeError("Evidence output path outside checkout")
        if output.exists():
            owner_file = output / "owned-run.json"
            if owner_file.is_symlink() or not owner_file.is_file():
                raise RuntimeError("Preexisting evidence output has no owned-run marker")
            owner = json.loads(owner_file.read_text(encoding="utf-8"))
            if owner != {"runId": run_id, "headSha": os.environ["GITHUB_SHA"], "owner": "seven-build14-android-emulator"}:
                raise RuntimeError("Preexisting evidence output belongs to another run")
        else:
            output.mkdir(parents=True, exist_ok=False)
            (output / "owned-run.json").write_text(json.dumps({"runId": run_id,
                "headSha": os.environ["GITHUB_SHA"], "owner": "seven-build14-android-emulator"}, indent=2) + "\n")
    name = f"seven-build14-android-emulator-{run_id}-attempt{attempt}.zip"
    archive = temp / name
    if archive.exists():
        raise RuntimeError("Evidence ZIP already exists; no overwrite")
    if any((output / name).exists() or (output / name).is_symlink()
           for name in ("step-outcomes.json", "failure-stage.json", "input-manifest.json",
                        "run-identity.json", "evidence-index.json")):
        raise RuntimeError("Evidence packaging already attempted; no overwrite")
    (output / "step-outcomes.json").write_text(json.dumps({"runId": run_id,
        "sourceCommit": m["source"]["sourceCommit"], "steps": outcomes,
        "storeWrites": 0, "firebaseWrites": 0}, indent=2) + "\n")
    if not (output / "native-observation.json").is_file():
        marker = output / "probe-not-started.json"
        if marker.exists() or marker.is_symlink():
            raise RuntimeError("Existing probe-not-started marker; no overwrite")
        marker.write_text(json.dumps({"status": "NO_NATIVE_PROBE_OUTPUT", "runId": run_id,
            "steps": outcomes}, indent=2) + "\n")
        (output / "failure-stage.json").write_text(json.dumps({
            "status": "NO_NATIVE_PROBE_OUTPUT", "runId": run_id,
            "steps": outcomes, "storeWrites": 0, "firebaseWrites": 0}, indent=2) + "\n")
    (output / "input-manifest.json").write_bytes((HERE / "manifest.json").read_bytes())
    (output / "run-identity.json").write_text(json.dumps({"runId": run_id, "attempt": attempt,
        "headSha": os.environ.get("GITHUB_SHA") if not args.dry_run else None,
        "apkSha256": m["apk"]["sha256"], "buildValidationSha256": m["source"]["buildValidationSha256"],
        "atUtc": dt.datetime.now(dt.timezone.utc).isoformat(), "storeWrites": 0, "firebaseWrites": 0}, indent=2) + "\n")
    entries = list(output.rglob("*"))
    if any(path.is_symlink() or not path.resolve().is_relative_to(output.resolve()) for path in entries):
        raise RuntimeError("Evidence symlink/outside path forbidden")
    files = sorted(path for path in entries if path.is_file() and path.name != "evidence-index.json")
    total = sum(path.stat().st_size for path in files)
    if total > 512 * 1024 * 1024:
        raise RuntimeError("Evidence exceeds bounded 512 MiB package")
    index = [{"path": path.relative_to(output).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)} for path in files]
    (output / "evidence-index.json").write_text(json.dumps({"files": index, "totalBytes": total}, indent=2) + "\n")
    files.append(output / "evidence-index.json")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in files:
            z.write(path, path.relative_to(output).as_posix())
    archive_sha = sha(archive)
    if args.dry_run:
        print(json.dumps({"status": "LOCAL_EVIDENCE_ZIP_VERIFIED", "file": str(archive), "bytes": archive.stat().st_size, "sha256": archive_sha}))
        return
    release_id = m["release"].get("releaseId")
    if type(release_id) is not int or release_id <= 0 or m.get("status") != "READY_FIXED_DRAFT_RELEASE":
        raise RuntimeError("Unique draft release ID not pinned; evidence ZIP kept on runner")
    release = get_release(release_id)
    if (release.get("id") != release_id or release.get("draft") is not True
            or release.get("tag_name") != m["release"]["tag"]
            or release.get("target_commitish") != RELEASE_TARGET):
        raise RuntimeError("Draft release identity changed; evidence ZIP kept on runner")
    if any(asset.get("name") == name for asset in release.get("assets", [])):
        raise RuntimeError("Evidence asset name already exists; no overwrite")
    result = subprocess.run(["gh", "release", "upload", m["release"]["tag"], str(archive), "--repo", REPO], capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError("Unique evidence upload returned nonzero; inspect release before any retry")
    readback = get_release(release_id)
    matches = [asset for asset in readback.get("assets", []) if asset.get("name") == name]
    if (readback.get("id") != release_id or readback.get("draft") is not True
            or readback.get("tag_name") != m["release"]["tag"]
            or readback.get("target_commitish") != RELEASE_TARGET
            or len(matches) != 1 or matches[0].get("state") != "uploaded"
            or matches[0].get("size") != archive.stat().st_size
            or matches[0].get("digest") != "sha256:" + archive_sha):
        raise RuntimeError("Evidence upload outcome uncertain; no retry")
    verify_dir = temp / (name + ".readback")
    if verify_dir.exists() or verify_dir.is_symlink():
        raise RuntimeError("Evidence readback directory already exists")
    verify_dir.mkdir()
    downloaded = verify_dir / name
    result = subprocess.run(["gh", "release", "download", m["release"]["tag"],
                             "--repo", REPO, "--pattern", name, "--dir", str(verify_dir)],
                            capture_output=True, timeout=180)
    if (result.returncode or not downloaded.is_file() or downloaded.is_symlink()
            or downloaded.stat().st_size != archive.stat().st_size
            or sha(downloaded) != archive_sha):
        raise RuntimeError("Draft evidence asset byte readback differs; no upload retry")
    print(json.dumps({"status": "ONE_SHOT_DRAFT_EVIDENCE_UPLOAD_VERIFIED", "releaseId": release_id,
        "assetId": matches[0]["id"], "name": name, "bytes": archive.stat().st_size, "sha256": archive_sha,
        "storeWrites": 0, "firebaseWrites": 0}))


if __name__ == "__main__":
    main()
