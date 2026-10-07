"""Future CI-only pinned SDK provisioning; never writes an owner's SDK."""
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from sdk_preflight import scope_guard

def main():
    scope_guard(os.environ, os.environ['NATIVE_AVD_NAME'])
    temp = Path(os.environ['RUNNER_TEMP']).resolve()
    sdk = temp / 'crack-swangle-sdk'
    if sdk.exists():
        raise RuntimeError('Fresh isolated SDK target required; no reuse/replacement')
    sdk.mkdir()
    pin = json.loads(Path(__file__).with_name('package-pin.json').read_text())
    archive = temp / 'official-emulator-16428233.zip'
    with urllib.request.urlopen(pin['archive']['url'], timeout=30) as source, archive.open('wb') as output:
        while block := source.read(1024 * 1024):
            output.write(block)
    actual={'bytes':archive.stat().st_size,'sha1':hashlib.file_digest(archive.open('rb'),'sha1').hexdigest(),'sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()}
    verified=actual['bytes']==pin['archive']['bytes'] and actual['sha1']==pin['archive']['checksum']
    output=Path(os.environ['GITHUB_WORKSPACE']).resolve()/'output/godot-swangle-preflight'
    output.mkdir(parents=True,exist_ok=True)
    (output/'bootstrap-archive-proof.json').write_text(json.dumps({'archivePath':str(archive),'expectedPin':pin['archive'],'actual':actual,'archiveVerifiedAgainstOfficialPin':verified},indent=2)+'\n')
    if not verified:
        raise RuntimeError('Pinned public SDK package did not verify; STOP')
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            target = sdk / entry.filename
            if not target.resolve().is_relative_to(sdk) or not entry.filename.startswith('emulator/'):
                raise RuntimeError('SDK archive path outside isolated scope')
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = package.read(entry)
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                link = raw.decode()
                if not (target.parent / link).resolve().is_relative_to(sdk):
                    raise RuntimeError('SDK archive symlink escapes isolated scope')
                target.symlink_to(link)
            else:
                target.write_bytes(raw)
                target.chmod((entry.external_attr >> 16) & 0o777 or 0o644)
    base = Path(os.environ['ANDROID_HOME']).resolve()
    if (base / 'licenses').is_dir():
        shutil.copytree(base / 'licenses', sdk / 'licenses')  # Existing accepted SDK license hashes, not credentials.
    manager = base / 'cmdline-tools/latest/bin/sdkmanager'
    subprocess.run([str(manager), '--sdk_root=' + str(sdk), '--install', 'platform-tools', 'build-tools;36.0.0', 'system-images;android-36;google_apis;x86_64', '--channel=0'], check=True)
    with Path(os.environ['GITHUB_ENV']).open('a') as output:
        output.write('ANDROID_HOME=' + str(sdk) + '\nANDROID_SDK_ROOT=' + str(sdk) + '\n')
        output.write('BASE_AVDMANAGER=' + str(base / 'cmdline-tools/latest/bin/avdmanager') + '\n')
        output.write('ANDROID_AVD_HOME=' + str(temp / 'crack-swangle-avds') + '\nANDROID_USER_HOME=' + str(temp / 'crack-swangle-user') + '\n')

if __name__ == '__main__':
    main()
