"""Fetch/verify only the approved frozen r6 inputs; never executes game/signing code."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

REPO = "mars-tw/taiwan-train-math"
TAG = "all-games-mobile-ci-20261007-r6"
RELEASE_ID = 405759139
MANIFEST_SHA = "5f647d1351119ca0d61aa2779ad9e33dc6e9afa3da34e7b68efb6517703ef6cc"
ZIP_SHA = "1abd7f426e81dc5d15aa84a38d23e6b7672fa8f0da011e1dce4d750dce78efc4"
FILES = {"SHA256SUMS": 262144, "ci_verify_ios.py": 1048576,
         "ci_ios_export.sh": 1048576, "ashes-convoy-ios-source.zip": 1073741824}

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def checksums(text):
    result = {}
    for line in text.splitlines():
        if not line.strip(): continue
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?([A-Za-z0-9][A-Za-z0-9._-]{0,150})", line)
        if not match or match[2] in result: raise ValueError("Invalid checksum manifest")
        result[match[2]] = match[1].lower()
    return result

def validate_release(release):
    if release.get("id") != RELEASE_ID or release.get("tag_name") != TAG or release.get("draft") is not True:
        raise ValueError("Approved draft release identity changed")
    if not set(FILES).issubset({item.get("name") for item in release.get("assets", [])}):
        raise ValueError("Approved input assets missing")

def verify(directory):
    if not directory.is_dir() or directory.is_symlink(): raise ValueError("Input directory missing/unsafe")
    if {path.name for path in directory.iterdir()} - set(FILES) - {"recording-input-provenance.json"}:
        raise ValueError("Unexpected recording input files")
    for name, maximum in FILES.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= maximum:
            raise ValueError("Missing/unsafe/oversized input")
    if digest(directory / "SHA256SUMS") != MANIFEST_SHA: raise ValueError("Checksum manifest changed")
    sums = checksums((directory / "SHA256SUMS").read_text(encoding="utf-8"))
    for name in FILES:
        if name != "SHA256SUMS" and (name not in sums or digest(directory / name) != sums[name]):
            raise ValueError("Frozen input bytes changed")
    if digest(directory / "ashes-convoy-ios-source.zip") != ZIP_SHA:
        raise ValueError("Exact submitted-payload source archive changed")
    return {name: digest(directory / name) for name in FILES}

def command(args):
    try:
        result = subprocess.run(args, capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Official input download did not finish; private output withheld") from None
    if result.returncode: raise ValueError("Official input download failed; private output withheld")
    return result.stdout

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("fetch", "verify"))
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_REPOSITORY") != REPO: raise ValueError("Unexpected caller repository")
    intended = Path(os.environ["RUNNER_TEMP"]).resolve()
    directory = args.directory.resolve()
    if directory == intended or not directory.is_relative_to(intended): raise ValueError("Inputs outside owned runner temporary directory")
    if args.mode == "fetch":
        directory.mkdir(parents=False, exist_ok=False)
        release = json.loads(command(["gh", "api", "--method", "GET", f"repos/{REPO}/releases/{RELEASE_ID}"]))
        validate_release(release)
        for name in FILES:
            command(["gh", "release", "download", TAG, "--repo", REPO, "--pattern", name, "--dir", str(directory)])
        hashes = verify(directory)
        provenance = {"repository": REPO, "releaseId": RELEASE_ID, "releaseTag": TAG,
                      "manifestSha256": MANIFEST_SHA, "filesSha256": hashes,
                      "sourceWorkflowCommit": os.environ.get("GITHUB_SHA"), "runId": os.environ.get("GITHUB_RUN_ID"),
                      "sourceOnly": True, "gameExecuted": False, "appleSecretsUsed": False}
        (directory / "recording-input-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    else:
        hashes = verify(directory)
        provenance = json.loads((directory / "recording-input-provenance.json").read_text(encoding="utf-8"))
        required = {"repository": REPO, "releaseTag": TAG, "sourceOnly": True, "gameExecuted": False, "appleSecretsUsed": False}
        if any(provenance.get(key) != value or type(provenance.get(key)) is not type(value) for key, value in required.items()):
            raise ValueError("Input relay provenance scope changed")
        if provenance.get("filesSha256") != hashes or provenance.get("releaseId") != RELEASE_ID or provenance.get("manifestSha256") != MANIFEST_SHA:
            raise ValueError("Same-run source relay changed")
        if provenance.get("sourceWorkflowCommit") != os.environ.get("GITHUB_SHA") or provenance.get("runId") != os.environ.get("GITHUB_RUN_ID"):
            raise ValueError("Input relay belongs to another run/commit")
    print(json.dumps({"status": "EXACT_R6_RECORDING_INPUTS_VERIFIED", "files": len(FILES), "sourceZipSha256": ZIP_SHA, "appleSecretsUsed": False}))

if __name__ == "__main__": main()
