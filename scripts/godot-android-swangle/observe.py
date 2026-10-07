"""Cold/warm native observations only. Never taps a game Start control."""
import csv
import hashlib
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
from sdk_preflight import scope_guard, PROJECT

APK_SHA = '0b408ad03249ea131aa0302b158fa13cce03c9b9e69a6ef8ddb548ee6afb843b'
CERT_SHA = '7166f66b5a182f2330c380fd57bd6f2821247db519b59ab9abe5aa554968c797'
PACKAGE = 'tw.mars.crackveilvanguard'

def now():
    return datetime.now(timezone.utc).isoformat()

def unique_ocr_candidate(rows, width, height, rendered_menu_reviewed=False):
    # Only a later, concretely reviewed native menu may propose a point.
    if not rendered_menu_reviewed:
        return None
    grouped = {}
    for row in rows:
        if row.get('level') != '5' or not row.get('text', '').strip():
            continue
        key = tuple(row.get(k) for k in ['page_num', 'block_num', 'par_num', 'line_num'])
        grouped.setdefault(key, []).append(row)
    candidates = []
    for words in grouped.values():
        words.sort(key=lambda row: int(row['left']))
        label = re.sub(r'\s+', '', ''.join(row['text'] for row in words)).upper()
        if label not in {'START', 'PLAY', '開始', '開始遊戲'} or any(float(row.get('conf', '-1')) < 90 for row in words):
            continue
        boxes = [(int(row['left']), int(row['top']), int(row['width']), int(row['height'])) for row in words]
        if any(not (0 <= x < x + w <= width and 0 <= y < y + h <= height) for x, y, w, h in boxes):
            continue
        l, t = min(b[0] for b in boxes), min(b[1] for b in boxes)
        r, b = max(v[0] + v[2] for v in boxes), max(v[1] + v[3] for v in boxes)
        candidates.append({'label': label, 'nativeBounds': [l, t, r, b], 'nativePoint': [(l + r) // 2, (t + b) // 2], 'basis': 'unique full OCR native text line plus later Root visual button confirmation'})
    return candidates[0] if len(candidates) == 1 else None

def main():
    avd = os.environ['NATIVE_AVD_NAME']; scope_guard(os.environ, avd)
    sdk = Path(os.environ['ANDROID_HOME']).resolve(); temp = Path(os.environ['RUNNER_TEMP']).resolve()
    if not sdk.is_relative_to(temp):
        raise RuntimeError('Isolated SDK required before any native command')
    output = Path(os.environ['GITHUB_WORKSPACE']).resolve() / 'output/godot-swangle-preflight'
    sdk_proof = json.loads((output / 'sdk-preflight.json').read_text())
    if sdk_proof['status'] != 'VERIFIED_PINNED_BACKEND_PREFLIGHT':
        raise RuntimeError('Backend preflight has not passed; STOP')
    source = temp / 'native-capture-input'
    manifest = json.loads((source / 'android-capture-manifest.json').read_text())
    item = next(x for x in manifest['projects'] if x['projectId'] == PROJECT)
    apk = source / item['apkFile']
    assert hashlib.sha256(apk.read_bytes()).hexdigest() == APK_SHA == item['apkSha256']
    assert item['certificateSha256'] == CERT_SHA and item['packageName'] == PACKAGE and item['version'] == '1.0.0' and item['build'] == 1
    report = {'status': 'PREPARING', 'runId': os.environ['GITHUB_RUN_ID'], 'headSha': os.environ['GITHUB_SHA'],
              'projectId': PROJECT, 'family': 'phone', 'avd': avd, 'physical': False, 'apkSha256': APK_SHA,
              'certificateSha256': CERT_SHA, 'packageName': PACKAGE, 'version': '1.0.0', 'build': 1,
              'gameStartTapped': False, 'menuRenderedVerified': False, 'wholeGameplayGoalComplete': False,
              'sourceOrRendererChanged': False, 'frames': [], 'commands': [], 'warnings': []}
    def save():
        (output / 'native-observation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    def command(args, timeout=30):
        result = subprocess.run(args, capture_output=True, timeout=timeout)
        report['commands'].append({'argv': args, 'atUtc': now(), 'exitCode': result.returncode, 'stderr': result.stderr.decode('utf-8', 'replace')})
        save()
        if result.returncode:
            raise RuntimeError('Fixed native command failed; STOP')
        return result.stdout
    adb = str(sdk / 'platform-tools/adb')
    def ad(*args, timeout=30):
        return command([adb, '-s', 'emulator-5554', *args], timeout)
    emulator_log = (output / 'owned-emulator.log').open('wb')
    argv = [str(sdk / 'emulator/emulator'), '-avd', avd, '-port', '5554', '-memory', '3072', '-no-window', '-gpu', 'swangle', '-feature', '-Vulkan', '-no-snapshot', '-no-audio', '-no-boot-anim', '-camera-back', 'none', '-camera-front', 'none']
    report['exactEmulatorArgv'] = argv; save()
    process = subprocess.Popen(argv, stdout=emulator_log, stderr=subprocess.STDOUT)
    report['ownedEmulatorPid'] = process.pid; save()
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Owned emulator exited before boot; STOP')
            result = subprocess.run([adb, '-s', 'emulator-5554', 'shell', 'getprop', 'sys.boot_completed'], capture_output=True, timeout=15)
            if result.returncode == 0 and result.stdout.strip() == b'1':
                break
            time.sleep(3)
        else:
            raise RuntimeError('Boot bound reached; STOP')
        assert ad('emu', 'avd', 'name').decode().splitlines()[0].strip() == avd
        ad('shell', 'input', 'keyevent', '82')  # Unlock only the known owned fresh CI phone, no game control.
        boot_log = (output / 'owned-emulator.log').read_text(encoding='utf-8', errors='replace')
        if 'gles_mode_selected:swangle' not in boot_log:
            raise RuntimeError('Boot log does not confirm exact SWANGLE selection; STOP before APK launch')
        report['actualBootGpuLines'] = [line for line in boot_log.splitlines() if 'gles_mode_selected:' in line or 'Graphics Adapter' in line or 'Graphics API Version' in line]
        report['buildFingerprint'] = ad('shell', 'getprop', 'ro.build.fingerprint').decode().strip()
        report['nativeBridge'] = ad('shell', 'getprop', 'ro.dalvik.vm.native.bridge').decode().strip()
        report['deviceAbiList'] = ad('shell', 'getprop', 'ro.product.cpu.abilist').decode().strip()
        assert ad('shell', 'getprop', 'ro.build.version.sdk').strip() == b'36'
        signed = command([str(sdk / 'build-tools/36.0.0/apksigner'), 'verify', '--verbose', '--print-certs', str(apk)]).decode()
        assert re.findall(r'certificate SHA-256 digest: ([0-9a-f]{64})', signed) == [CERT_SHA]
        badging = command([str(sdk / 'build-tools/36.0.0/aapt'), 'dump', 'badging', str(apk)]).decode()
        assert "package: name='" + PACKAGE + "' versionCode='1' versionName='1.0.0'" in badging and 'application-debuggable' not in badging
        assert b'Success' in ad('install', '--no-streaming', str(apk), timeout=120)
        component = ad('shell', 'cmd', 'package', 'resolve-activity', '--brief', PACKAGE).decode().strip().splitlines()[-1]
        assert component.startswith(PACKAGE + '/')
        ad('shell', 'am', 'start', '-W', '-n', component); launched = time.monotonic()
        for label, seconds in [('cold', 8), ('warm', 90)]:
            time.sleep(max(0, launched + seconds - time.monotonic()))
            foreground = ad('shell', 'dumpsys', 'activity', 'activities').decode('utf-8', 'replace')
            active = [line.strip() for line in foreground.splitlines() if 'ResumedActivity' in line]
            assert any(PACKAGE + '/' in line for line in active)
            raw = ad('exec-out', 'screencap', '-p'); rawpath = output / (label + '-raw-native.png'); rawpath.write_bytes(raw)
            with Image.open(rawpath) as image:
                image.load(); assert image.size in {(1080, 1920), (1920, 1080)}
                assert image.mode != 'RGBA' or image.getchannel('A').getextrema() == (255, 255)
                rgb = image.convert('RGB'); path = output / (label + '.png'); rgb.save(path)
                assert Image.open(path).convert('RGB').tobytes() == rgb.tobytes()
                report['frames'].append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'rawFile': rawpath.name, 'rawSha256': hashlib.sha256(raw).hexdigest(), 'pixelSha256': hashlib.sha256(rgb.tobytes()).hexdigest(), 'width': image.width, 'height': image.height, 'capturedAtUtc': now(), 'nativeForeground': active, 'nativePixelsUnchanged': True})
            (output / (label + '-power-state.txt')).write_bytes(ad('shell', 'dumpsys', 'power'))
            try:
                ad('shell', 'uiautomator', 'dump', '--compressed', '/sdcard/swangle-own.xml')
                (output / (label + '.xml')).write_bytes(ad('exec-out', 'cat', '/sdcard/swangle-own.xml'))
            except Exception as error:
                report['warnings'].append('AX observation: ' + str(error))
            save()
        languages = command(['tesseract', '--list-langs']).decode()
        report['ocrVersion'] = command(['tesseract', '--version']).decode()
        report['ocrLanguages'] = languages
        assert {'chi_tra', 'eng'} <= set(languages.splitlines())
        report['ocrDistributionPackages'] = command(['dpkg-query', '-W', '-f=${Package}=${Version}\n', 'tesseract-ocr', 'tesseract-ocr-chi-tra']).decode()
        model_files = command(['dpkg', '-L', 'tesseract-ocr-chi-tra']).decode().splitlines()
        model = next(Path(path) for path in model_files if path.endswith('/chi_tra.traineddata'))
        report['chiTraModelSha256'] = hashlib.sha256(model.read_bytes()).hexdigest()
        command(['tesseract', str(output / 'warm.png'), str(output / 'warm-ocr'), '-l', 'chi_tra+eng', '--oem', '1', '--psm', '11', 'tsv'])
        report['ocrMenuProposalOnly'] = True; report['ocrCandidate'] = None
        # No Start point is used: menu/frame review is the next bounded proof phase.
        pid = ad('shell', 'pidof', PACKAGE).decode().strip()
        if pid.isdigit():
            own_log = ad('logcat', '-d', '--pid=' + pid, '-v', 'brief').decode('utf-8', 'replace')
            (output / 'own-app-logcat.log').write_text(own_log, encoding='utf-8')
            report['actualGlLines'] = [line for line in own_log.splitlines() if 'OpenGL API' in line or 'renderingDevice:' in line or 'renderer:' in line]
            report['shaderLinkFailureObserved'] = 'Program linking failed' in own_log
            if not re.search(r'ANGLE|SwANGLE|Subzero', '\n'.join(report['actualGlLines']), re.I):
                raise RuntimeError('Requested SWANGLE is not confirmed in actual guest GL lines; STOP')
            if 'renderingDevice: opengl3' not in own_log or 'renderer: gl_compatibility' not in own_log or 'Godot Engine v4.7.2.stable.official.ed1daf0bf' not in own_log:
                raise RuntimeError('Original Godot driver/engine tuple not confirmed; STOP')
            if report['shaderLinkFailureObserved']:
                raise RuntimeError('Original shader linking still failed; preserve cold/warm proof and STOP')
        else:
            raise RuntimeError('Own app PID/log unavailable; STOP')
        report['status'] = 'COLD_WARM_CAPTURED_ROOT_MENU_REVIEW_PENDING'
    except Exception as error:
        report.update(status='HOLD_OBSERVATION_STOP', error=str(error), noFallbackAttempted=True)
        raise
    finally:
        save()
        process.terminate()  # Only this script's exact child PID, never another AVD.
        emulator_log.close()

if __name__ == '__main__':
    main()
