"""Download only a future approved DRAFT diagnostic input. No release mutation."""
import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

REPO = 'mars-tw/taiwan-train-math'
TAG = 'crack-ocr-diagnostic-20261008-menu-37705000018'
IMAGE_SHA = '6f954c557987e002ea9cc5672de31654c146861b0ddfd8ddf2e3fc0e028ac947'
IMAGE_BYTES = 2964682
MANIFEST_SHA = '9603c26c869e7f4caafce284a6282c32bce01b81ff5cb6b3d4455db749a617e3'

def gh(resource):
    result = subprocess.run(['gh', 'api', resource, '-H', 'Accept: application/octet-stream'],
                            capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Official input GET failed; authenticated raw output suppressed')
    return result.stdout

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--manifest-sha', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    assert args.release_id.isdigit() and os.environ.get('GITHUB_REPOSITORY') == REPO
    assert args.manifest_sha == MANIFEST_SHA
    directory = args.directory.resolve()
    assert directory.is_relative_to(Path(os.environ['RUNNER_TEMP']).resolve())
    directory.mkdir(parents=True, exist_ok=False)
    release = json.loads(gh(f'repos/{REPO}/releases/{args.release_id}'))
    assert release['id'] == int(args.release_id) and release['draft'] is True
    assert release['tag_name'] == TAG and release['prerelease'] is False
    assets = release['assets']
    assert len(assets) == 2 and {a['name'] for a in assets} == {'fresh-clean-menu.png', 'ocr-input-manifest.json'}
    assets = {a['name']: a for a in assets}
    def download(name, expected_sha, expected_bytes=None):
        asset = assets[name]
        assert isinstance(asset['id'], int) and isinstance(asset['size'], int)
        assert 0 < asset['size'] <= (IMAGE_BYTES if name.endswith('.png') else 16384)
        if expected_bytes is not None:
            assert asset['size'] == expected_bytes
        raw = gh(f'repos/{REPO}/releases/assets/{asset["id"]}')
        assert len(raw) == asset['size'] and hashlib.sha256(raw).hexdigest() == expected_sha
        (directory/name).write_bytes(raw)
        return raw
    manifest = json.loads(download('ocr-input-manifest.json', args.manifest_sha))
    assert manifest['schemaVersion'] == 1 and manifest['repository'] == REPO
    assert manifest['sourceRunId'] == 37705000018 and manifest['image']['sha256'] == IMAGE_SHA
    assert manifest['sourceHeadSha'] == 'ba994d568996ca0e80f872402d302c0de595df96'
    assert manifest['projectId'] == 'crackveil-vanguard'
    assert manifest['image']['bytes'] == IMAGE_BYTES and manifest['image']['width'] == 1920
    assert manifest['image']['height'] == 1080 and manifest['image']['mode'] == 'RGB'
    download('fresh-clean-menu.png', IMAGE_SHA, IMAGE_BYTES)
    (directory/'fetch-provenance.json').write_text(json.dumps({
        'releaseId': int(args.release_id), 'draft': True, 'releaseTag': TAG,
        'manifestSha256': args.manifest_sha, 'imageSha256': IMAGE_SHA,
        'imageBytes': IMAGE_BYTES, 'storeCredentialUsed': False, 'appStarted': False,
    }, indent=2)+'\n', encoding='utf-8')

if __name__ == '__main__':
    main()
