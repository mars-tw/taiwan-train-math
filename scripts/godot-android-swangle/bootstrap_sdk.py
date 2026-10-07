"""Future CI-only pinned SDK provisioning; never writes an owner's SDK."""
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from sdk_preflight import scope_guard


def tree_manifest(folder):
    rows=[]
    for path in sorted(folder.rglob('*')):
        if path.is_symlink():
            if not path.resolve().is_relative_to(folder):
                raise RuntimeError('Vendor tool symlink escapes package; STOP')
            rows.append({'path':path.relative_to(folder).as_posix(),'type':'symlink','target':os.readlink(path)})
        elif path.is_file():
            rows.append({'path':path.relative_to(folder).as_posix(),'type':'regular','bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return rows

def properties(file):
    text=file.read_text(encoding='utf-8')
    return dict(line.split('=',1) for line in text.splitlines() if '=' in line and not line.lstrip().startswith('#'))

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
    vendor=(base/'cmdline-tools/latest').resolve()
    if not vendor.is_relative_to(base/'cmdline-tools') or not (vendor/'bin/avdmanager').is_file() or not (vendor/'source.properties').is_file():
        raise RuntimeError('Known vendor command-line package unavailable; STOP')
    source_properties=properties(vendor/'source.properties')
    if 'Command-line' not in source_properties.get('Pkg.Desc','') or not source_properties.get('Pkg.Revision'):
        raise RuntimeError('Vendor tool version/description not identifiable; STOP')
    source_manifest=tree_manifest(vendor)
    isolated_tools=sdk/'cmdline-tools/baseline'
    shutil.copytree(vendor,isolated_tools,symlinks=True)
    copied_manifest=tree_manifest(isolated_tools)
    if source_manifest!=copied_manifest:
        raise RuntimeError('Copied vendor tools byte/type manifest mismatch; STOP')
    tool_proof={'sourcePackagePath':str(vendor),'isolatedPackagePath':str(isolated_tools),'actualSourceProperties':source_properties,'sourcePropertiesSha256':hashlib.sha256((vendor/'source.properties').read_bytes()).hexdigest(),'sourceManifest':source_manifest,'copiedManifest':copied_manifest,'copyExactlyMatchesSource':True,'officialRunnerSdkPackageArchiveChecksumNotIndependentlyAvailable':True}
    (output/'isolated-cmdline-tools-proof.json').write_text(json.dumps(tool_proof,indent=2)+'\n')
    if (base / 'licenses').is_dir():
        shutil.copytree(base / 'licenses', sdk / 'licenses')  # Existing accepted SDK license hashes, not credentials.
    manager = isolated_tools / 'bin/sdkmanager'
    subprocess.run([str(manager), '--sdk_root=' + str(sdk), '--install', 'platform-tools', 'build-tools;36.0.0', 'system-images;android-36;google_apis;x86_64', '--channel=0'], check=True)
    image=sdk/'system-images/android-36/google_apis/x86_64'
    package_xml=image/'package.xml'; source_prop=image/'source.properties'
    if not package_xml.is_file() or not source_prop.is_file():
        raise RuntimeError('Exact isolated image schema unavailable; STOP')
    tree=ET.fromstring(package_xml.read_bytes())
    local=next((node for node in tree.iter() if node.tag.split('}')[-1]=='localPackage'),None)
    prop=properties(source_prop)
    if local is None or local.get('path')!='system-images;android-36;google_apis;x86_64' or prop.get('AndroidVersion.ApiLevel')!='36' or prop.get('SystemImage.Abi')!='x86_64':
        raise RuntimeError('Installed image API/ABI/package identity mismatch; STOP')
    schema={'actualSdkRoot':str(sdk),'actualAvdManager':str(isolated_tools/'bin/avdmanager'),'imagePath':str(image),'localPackagePath':local.get('path'),'sourceProperties':prop,'packageXmlSha256':hashlib.sha256(package_xml.read_bytes()).hexdigest(),'sourcePropertiesSha256':hashlib.sha256(source_prop.read_bytes()).hexdigest(),'toolPackageRevision':source_properties['Pkg.Revision'],'targetLookupRootFromCanonicalToolLocation':str(isolated_tools.parent.parent)}
    (output/'isolated-sdk-image-schema.json').write_text(json.dumps(schema,indent=2)+'\n')
    with Path(os.environ['GITHUB_ENV']).open('a') as output:
        output.write('ANDROID_HOME=' + str(sdk) + '\nANDROID_SDK_ROOT=' + str(sdk) + '\n')
        output.write('ISOLATED_AVDMANAGER=' + str(isolated_tools / 'bin/avdmanager') + '\n')
        output.write('ANDROID_AVD_HOME=' + str(temp / 'crack-swangle-avds') + '\nANDROID_USER_HOME=' + str(temp / 'crack-swangle-user') + '\n')

if __name__ == '__main__':
    main()
