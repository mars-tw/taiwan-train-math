"""Pinned SDK/backend checks in a fresh CI VM. STOP, never select a fallback."""
import ctypes
import hashlib
import json
import os
import re
import stat
import subprocess
import urllib.request
import zipfile
from pathlib import Path

PROJECT = 'crackveil-vanguard'

def verified_frontend_text(record):
    if record.get('exitCode')!=0 or record.get('timedOut') is not False or record.get('toolUnavailable'):
        raise RuntimeError('Frontend command failed/unavailable/timed out; STOP before context')
    values=[]
    for key in ['stdout','stderr']:
        stream=record.get(key)
        if not isinstance(stream,dict) or stream.get('truncated') is not False or not isinstance(stream.get('text'),str) or not isinstance(stream.get('fullBytes'),int) or stream['fullBytes']<0:
            raise RuntimeError('Frontend stream truncated/incomplete; STOP before context')
        values.append(stream['text'])
    return ''.join(values)

def verified_bundle_inventory(sdk, package, missing_names):
    rows=[]; library_dirs=set()
    for name in missing_names:
        members=[member for member in package.namelist() if member.startswith('emulator/lib64/') and Path(member).name==name]
        if len(members)!=1:
            rows.append({'name':name,'verified':False,'reason':'archive membership absent/nonunique','members':members}); continue
        member=members[0]; installed=sdk/member
        if not installed.resolve().is_relative_to(sdk/'emulator/lib64') or not installed.is_file():
            raise RuntimeError('Bundled library escapes verified own SDK scope; STOP')
        info=package.getinfo(member); raw=package.read(member)
        symlink=(info.external_attr>>16)&0o170000==0o120000
        if symlink:
            link=raw.decode()
            if not installed.is_symlink() or os.readlink(installed)!=link:
                raise RuntimeError('Bundled library symlink does not match frozen archive; STOP')
            # Match the resolved own-SDK file against its exact archive member.
            resolved_member=installed.resolve().relative_to(sdk).as_posix()
            target_info=package.getinfo(resolved_member)
            if (target_info.external_attr>>16)&0o170000==0o120000 or not stat.S_ISREG(installed.resolve().lstat().st_mode):
                raise RuntimeError('Resolved archive symlink target type mismatch; STOP')
            reference=package.read(resolved_member)
        else:
            if installed.is_symlink() or not stat.S_ISREG(installed.lstat().st_mode):
                raise RuntimeError('Archived regular library installed type mismatch; STOP')
            resolved_member=member; reference=raw
        actual=installed.read_bytes(); verified=hashlib.sha256(actual).digest()==hashlib.sha256(reference).digest()
        rows.append({'name':name,'archiveMember':member,'resolvedArchiveMember':resolved_member,'installedPath':str(installed),'actualSha256':hashlib.sha256(actual).hexdigest(),'archiveFileSha256':hashlib.sha256(reference).hexdigest(),'verified':verified})
        if verified:library_dirs.add(str(installed.parent.resolve()))
    return rows,sorted(library_dirs)

def own_qemu_evidence(sdk, reference_bytes):
    child=sdk/'emulator/qemu/linux-x86_64/qemu-system-x86_64'
    real=child.resolve()
    if not real.is_relative_to(sdk/'emulator/qemu/linux-x86_64') or not child.is_file():
        raise RuntimeError('Exact owned QEMU child scope mismatch; STOP')
    raw=child.read_bytes()
    row={'path':str(child),'realpath':str(real),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'elfMagic':raw[:4].hex(),'executable':os.access(child,os.X_OK)}
    if raw[:4]!=b'\x7fELF' or not row['executable'] or hashlib.sha256(raw).digest()!=hashlib.sha256(reference_bytes).digest():
        raise RuntimeError('Owned QEMU ELF/executable/archive byte proof failed; STOP')
    return row

def missing_child_libraries(record):
    return re.findall(r'^\s*(\S+)\s+=>\s+not found\s*$',record.get('stdout',{}).get('text',''),re.M)

def probe_text(raw, limit=8192):
    value=raw[:limit].decode('utf-8','backslashreplace')
    value=''.join('\\u%04x'%ord(c) if ord(c)<32 and c not in '\r\n\t' else c for c in value)
    return {'text':value,'fullBytes':len(raw),'retainedBytes':min(len(raw),limit),'capBytes':limit,'truncated':len(raw)>limit,'sha256':hashlib.sha256(raw).hexdigest()}

def diagnostic_probe(argv, record, persist, timeout=15, env=None, readback_limit=8192):
    # The caller restricts these argv to the verified own-SDK binary only.
    if readback_limit not in (8192,16384):
        raise RuntimeError('Unsupported diagnostic cap; STOP')
    try:
        result=subprocess.run(argv,capture_output=True,timeout=timeout,env=env)
        record.update(argv=argv,exitCode=result.returncode,stdout=probe_text(result.stdout,readback_limit),stderr=probe_text(result.stderr,readback_limit),timedOut=False)
    except subprocess.TimeoutExpired as error:
        record.update(argv=argv,exitCode=None,stdout=probe_text(error.stdout or b'',readback_limit),stderr=probe_text(error.stderr or b'',readback_limit),timedOut=True)
    except FileNotFoundError:
        record.update(argv=argv,exitCode=None,toolUnavailable=True,stdout=probe_text(b'',readback_limit),stderr=probe_text(b'',readback_limit),timedOut=False)
    persist()
    return record

def scope_guard(env, avd):
    run_id = env.get('GITHUB_RUN_ID', '')
    if env.get('GITHUB_ACTIONS') != 'true' or env.get('GITHUB_REPOSITORY') != 'mars-tw/taiwan-train-math' or not run_id.isdigit():
        raise RuntimeError('Owned GitHub CI only')
    if avd != 'NativeCapturePhone_' + run_id + '_' + PROJECT:
        raise RuntimeError('Exact owned Crack phone AVD required')

def backend_guard(version, help_text, archive_sha1, pin, dependencies_present):
    if not re.search(r'Android emulator version 37\.2\.12\.0\b', version):
        raise RuntimeError('Pinned SDK version unavailable; STOP')
    if not re.search(r'(?<![\w])swangle(?![\w])', help_text):
        raise RuntimeError('SWANGLE not advertised; STOP')
    if archive_sha1 != pin['archive']['checksum']:
        raise RuntimeError('Official SDK archive checksum mismatch; STOP')
    if not dependencies_present:
        raise RuntimeError('Bundled ANGLE/Vulkan dependency missing; STOP')

def main():
    scope_guard(os.environ, os.environ['NATIVE_AVD_NAME'])
    sdk = Path(os.environ['ANDROID_HOME']).resolve()
    temp = Path(os.environ['RUNNER_TEMP']).resolve()
    if not sdk.is_relative_to(temp):
        raise RuntimeError('SDK must be isolated inside this CI run temporary directory')
    output = Path(os.environ['GITHUB_WORKSPACE']).resolve() / 'output/godot-swangle-preflight'
    output.mkdir(parents=True, exist_ok=True)
    pin = json.loads(Path(__file__).with_name('package-pin.json').read_text(encoding='utf-8'))
    assert pin['revision'] == '37.2.12' and pin['channel'] == 'channel-0'
    exe = sdk / 'emulator/emulator'
    report = {'status': 'PREPARING', 'projectId': PROJECT, 'family': 'phone', 'physical': False,
              'runId': os.environ['GITHUB_RUN_ID'], 'avd': os.environ['NATIVE_AVD_NAME'],
              'sdkPath': str(sdk), 'gpuRequested': 'swangle', 'fallbackAllowed': False, 'archivePin': pin['archive']}
    def save():
        (output / 'sdk-preflight.json').write_text(json.dumps(report, indent=2) + '\n')
    try:
        real=exe.resolve()
        if not real.is_relative_to(sdk / 'emulator') or not exe.is_file():
            raise RuntimeError('Owned isolated emulator binary scope mismatch; STOP')
        report['binaryEvidence']={'path':str(exe),'realpath':str(real),'executable':os.access(exe,os.X_OK),'mode':oct(exe.stat().st_mode & 0o777),'bytes':exe.stat().st_size,'elfMagic':exe.open('rb').read(4).hex()}
        report['binarySha256']=hashlib.sha256(exe.read_bytes()).hexdigest()
        archive=temp/'official-emulator-16428233.zip'
        if archive.is_file():
            report['archiveActual']={'path':str(archive),'bytes':archive.stat().st_size,'sha1':hashlib.file_digest(archive.open('rb'),'sha1').hexdigest(),'sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()}
            report['archiveActualMatchesExpected']=report['archiveActual']['bytes']==pin['archive']['bytes'] and report['archiveActual']['sha1']==pin['archive']['checksum']
        else:
            report['archiveActual']=None
            report['archiveActualMatchesExpected']=False
        bootstrap=output/'bootstrap-archive-proof.json'
        report['bootstrapProof']=json.loads(bootstrap.read_text()) if bootstrap.is_file() else None
        save()
        if report['archiveActualMatchesExpected'] is not True:
            raise RuntimeError('Actual archive did not match frozen official pin; STOP')
        with zipfile.ZipFile(archive) as owned_package:
            if hashlib.sha256(owned_package.read('emulator/emulator')).hexdigest()!=report['binarySha256']:
                raise RuntimeError('Owned binary does not match verified official archive; STOP')
        report['loaderDiagnostics']={}
        for key,argv in [('ldd',['ldd',str(real)]),('readelfDynamic',['readelf','-d',str(real)])]:
            row=report['loaderDiagnostics'].setdefault(key,{})
            diagnostic_probe(argv,row,save)
        with zipfile.ZipFile(archive) as verified_package:
            report['qemuChildEvidence']=own_qemu_evidence(sdk,verified_package.read('emulator/qemu/linux-x86_64/qemu-system-x86_64'))
        save()
        child=report['qemuChildEvidence']['realpath']
        child_diagnostics=report.setdefault('qemuChildDiagnostics',{})
        for key,argv in [('ldd',['ldd',child]),('readelfDynamic',['readelf','-d',child])]:
            diagnostic_probe(argv,child_diagnostics.setdefault(key,{}),save,readback_limit=16384 if key=='ldd' else 8192)
        missing=missing_child_libraries(child_diagnostics['ldd'])
        report['qemuChildMissingDependencies']=missing
        save()
        # Plain direct-child ldd lacks the launcher's library search setup.
        # Retain it as a diagnostic, and measure genuine frontend execution first.
        report['directChildLddIsDiagnosticNotLaunchVerdict']=True
        save()
        probes=report.setdefault('binaryCommands',{})
        version_probe=diagnostic_probe([str(real),'-version'],probes.setdefault('version',{}),save)
        version=verified_frontend_text(version_probe)
        help_probe=diagnostic_probe([str(real),'-help-gpu'],probes.setdefault('gpuHelp',{}),save)
        help_text=verified_frontend_text(help_probe)
        report.update(versionText=version,gpuHelpText=help_text)
        save()
        backend_guard(version,help_text,report['archiveActual']['sha1'],pin,True)
        with zipfile.ZipFile(archive) as verified_package:
            inventory,owned_dirs=verified_bundle_inventory(sdk,verified_package,missing)
        report['directMissingBundleInventory']=inventory;save()
        if any(not item['verified'] for item in inventory):
            raise RuntimeError('Direct missing entry is not proven present in frozen SDK archive; STOP, do not guess packages')
        # Diagnostic subprocess only. Never changes os.environ/GITHUB_ENV or
        # app/AVD launch environment, and never appends a host search path.
        child_env=os.environ.copy()
        child_env['LD_LIBRARY_PATH']=':'.join(owned_dirs)
        report['childDiagnosticLibraryDirs']=owned_dirs
        report['actualLauncherChildEnvironmentCaptured']=False
        contextual=report.setdefault('qemuVendorLayoutDiagnostics',{})
        for key,argv in [('ldd',['ldd',child]),('readelfDynamic',['readelf','-d',child])]:
            diagnostic_probe(argv,contextual.setdefault(key,{}),save,env=child_env,readback_limit=16384 if key=='ldd' else 8192)
        report['contextualMissingDependencies']=missing_child_libraries(contextual['ldd']);save()
        if report['contextualMissingDependencies'] or any(row.get('exitCode')!=0 or row.get('stdout',{}).get('truncated') or row.get('stderr',{}).get('truncated') for row in contextual.values()):
            raise RuntimeError('Verified SDK-layout child context unresolved/incomplete; STOP')
        backend_guard(version, help_text, pin['archive']['checksum'], pin, True)
        # Retrieve only the pinned public package; never replace the installed SDK.
        archive = temp / 'official-emulator-16428233.zip'
        if not archive.exists():
            with urllib.request.urlopen(pin['archive']['url'], timeout=30) as response, archive.open('wb') as target:
                while block := response.read(1024 * 1024):
                    target.write(block)
        if archive.stat().st_size != pin['archive']['bytes']:
            raise RuntimeError('Pinned archive size mismatch; STOP')
        archive_sha1 = hashlib.file_digest(archive.open('rb'), 'sha1').hexdigest()
        report.update(archiveSha1=archive_sha1, archiveSha256=hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest())
        if archive_sha1 != pin['archive']['checksum']:
            raise RuntimeError('Official SDK archive checksum mismatch; STOP')
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
            reference_binary = hashlib.sha256(package.read('emulator/emulator')).hexdigest()
            if reference_binary != report['binarySha256']:
                raise RuntimeError('Installed binary differs from pinned official package; STOP')
            # Resolve bundled names from this exact archive, rather than guess DLL paths.
            angle_names = [n for n in names if n.endswith('.so') and ('angle' in n.lower() or 'swangle' in n.lower())]
            loader_names = [n for n in names if n.endswith('/libvulkan.so') or n.endswith('/libvulkan.so.1')]
            swiftshader_names = [n for n in names if n.endswith('/libvk_swiftshader.so')]
            if not angle_names or not loader_names or not swiftshader_names:
                raise RuntimeError('Pinned package does not contain required backend libraries; STOP')
            checked = []
            for name in angle_names + loader_names + swiftshader_names:
                path = sdk / name
                if not path.resolve().is_relative_to(sdk):
                    raise RuntimeError('SDK dependency path escapes this isolated SDK; STOP')
                info = package.getinfo(name)
                expected = package.read(name)
                symlink = (info.external_attr >> 16) & 0o170000 == 0o120000
                matches = path.is_symlink() and os.readlink(path) == expected.decode() if symlink else path.is_file() and hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(expected).digest()
                if not matches:
                    raise RuntimeError('Installed backend library differs from pinned archive; STOP')
                checked.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
                linked = subprocess.check_output(['ldd', str(path)], stderr=subprocess.STDOUT).decode('utf-8', 'replace')
                if 'not found' in linked:
                    raise RuntimeError('Backend shared-library dependency not found; STOP')
            ctypes.CDLL(str(sdk / loader_names[0]))  # Loads the declared host loader; no device/GPU instance is created.
        backend_guard(version, help_text, archive_sha1, pin, True)
        report.update(status='VERIFIED_PINNED_BACKEND_PREFLIGHT', backendLibraries=checked,
                      hostVulkanLoaderLoadable=True, nativeGpuContextNotYetCreated=True,
                      gameRendererChanged=False, sdkReplaced=False)
    except Exception as error:
        report.update(status='HOLD_PREFLIGHT_STOP', error=str(error), noFallbackAttempted=True)
        raise
    finally:
        save()

if __name__ == '__main__':
    main()
