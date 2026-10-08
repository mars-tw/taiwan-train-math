"""One fixed game/run: official artifact -> Root-owned DRAFT approval -> same driver."""
import argparse
import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image

REPO = 'mars-tw/taiwan-train-math'
APP = 'tw.mars.crackveilvanguard'
REVIEWER = '01a10a13-a7d2-71f1-a659-d79eae9200cf'
APPROVAL_TAG = 'crack-root-visible-start-approvals-20261008'
BINDINGS = ['repository', 'runId', 'runAttempt', 'headSha', 'captureId', 'avd',
            'serial', 'driverPid', 'driverStartTicks', 'emulatorPid', 'emulatorStartTicks',
            'appId', 'appPid', 'apkSha256', 'certificateSha256', 'frameSha256',
            'framePixelSha256', 'width', 'height', 'approvalDeadlineUnix', 'approvalAssetName']

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):
    return json.loads(path.read_text(encoding='utf-8'))
def write(path, value):
    temp = path.with_name(path.name+'.pending')
    temp.write_text(json.dumps(value, ensure_ascii=True, indent=2)+'\n', encoding='utf-8')
    temp.replace(path)
def ticks(pid):
    try:
        fields = (Path('/proc')/str(pid)/'stat').read_text().rsplit(')', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except OSError:
        return None
def same_process(pid, start_ticks):
    return start_ticks is not None and ticks(pid) == start_ticks
def output_dir():
    assert os.environ['GITHUB_REPOSITORY'] == REPO
    return Path(os.environ['GITHUB_WORKSPACE']).resolve()/'output/godot-swangle-preflight'
def gh(resource, binary=False):
    prefix = f'repos/{REPO}/releases/' + ('assets/' if binary else '')
    assert resource.startswith(prefix) and resource.removeprefix(prefix).isdigit()
    accept = 'application/octet-stream' if binary else 'application/vnd.github+json'
    result = subprocess.run(['gh', 'api', resource, '-H', 'Accept: '+accept], capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError('Official fixed-route approval GET failed; no authenticated raw output printed')
    return result.stdout

def core_geometry(approved, fresh, bounds):
    # Read only the original full images. No edited/cropped/resized image is produced.
    with Image.open(approved) as first, Image.open(fresh) as second:
        assert first.mode == second.mode == 'RGB' and first.size == second.size
        a, b = first.load(), second.load()
        left, top, right, bottom = bounds
        core = [(x, y) for y in range(top, bottom) for x in range(left, right)
                if min(a[x, y]) >= 185 and max(a[x, y])-min(a[x, y]) <= 50]
        assert len(core) >= 50, 'Root button region lacks stable visible text pixels'
        matching = sum(min(b[x, y]) >= 185 and max(b[x, y])-min(b[x, y]) <= 50 for x, y in core)
        ratio = matching/len(core)
        if ratio < 0.95:
            raise RuntimeError('Fresh visible button text/position changed; no Start intent')
        return {'approvedVisibleTextCorePixels': len(core), 'samePositionCorePixels': matching,
                'samePositionCoreRatio': ratio, 'fullBackgroundPixelEqualityRequired': False,
                'rootMeasuredNativeBounds': bounds, 'imagePixelsEdited': False}

def await_root_candidate(output, report, save, menu, ad, capture, ui_guard, process):
    app_pid = ad('shell', 'pidof', APP).decode().strip()
    assert app_pid.isdigit()
    request = {'schemaVersion': 1, 'repository': REPO, 'runId': report['runId'],
        'runAttempt': os.environ['GITHUB_RUN_ATTEMPT'], 'headSha': report['headSha'],
        'captureId': secrets.token_hex(12), 'avd': report['avd'], 'serial': 'emulator-5554',
        'driverPid': os.getpid(), 'driverStartTicks': ticks(os.getpid()),
        'emulatorPid': process.pid, 'emulatorStartTicks': ticks(process.pid),
        'appId': APP, 'appPid': app_pid, 'apkSha256': report['apkSha256'],
        'certificateSha256': report['certificateSha256'], 'frameFile': menu['file'],
        'frameSha256': menu['sha256'], 'framePixelSha256': menu['pixelSha256'],
        'width': menu['width'], 'height': menu['height'],
        'capturedAtUtc': menu['capturedAtUtc'], 'approvalDeadlineUnix': time.time()+600,
        'approvalAssetName': f'root-start-{report["runId"]}-{os.environ["GITHUB_RUN_ATTEMPT"]}.json'}
    assert request['driverStartTicks'] and request['emulatorStartTicks']
    report.update(status='WAIT_ROOT_FRESH_VISIBLE_APPROVAL', rootVisibleRequest=request,
                  ocrNotUsedForRootVisibleRoute=True)
    save()
    write(output/'root-visible-request.json', request) # Publish readiness only after its report is durable.
    approval_file = output/'root-start-approval.json'
    while not approval_file.is_file():
        if time.time() >= request['approvalDeadlineUnix'] or process.poll() is not None:
            raise RuntimeError('Root approval deadline/owned emulator ended; no Start intent')
        time.sleep(1)
    approval = read(approval_file)
    assert all(approval.get(k) == request[k] for k in BINDINGS)
    assert approval['schemaVersion'] == 1 and approval['action'] == 'START_ONCE'
    assert approval.get('rootActuallyViewedFreshArtifact') is True
    assert approval['reviewerThreadId'] == REVIEWER and approval['visibleLabel'] == '開始出擊'
    assert time.time() < approval['expiresAtUnix'] <= request['approvalDeadlineUnix']
    bounds = approval['nativeBounds']
    assert len(bounds) == 4 and all(type(v) is int for v in bounds)
    left, top, right, bottom = bounds
    assert 0 <= left < right <= menu['width'] and 0 <= top < bottom <= menu['height']
    assert ad('emu', 'avd', 'name').decode().splitlines()[0].strip() == request['avd']
    assert same_process(process.pid, request['emulatorStartTicks'])
    assert ad('shell', 'pidof', APP).decode().strip() == request['appPid']
    fresh = capture('immediate-before-root-start')
    assert (fresh['width'], fresh['height']) == (menu['width'], menu['height'])
    nodes = [n.attrib for n in ET.fromstring((output/'immediate-before-root-start.xml').read_bytes()).iter('node')]
    ui_guard(nodes, fresh['width'], fresh['height'], False)
    geometry = core_geometry(output/menu['file'], output/fresh['file'], bounds)
    assert ad('shell', 'pidof', APP).decode().strip() == request['appPid']
    report['rootVisibleApproval'] = {'approvedAssetSha256': sha(approval_file),
        'reviewedFrameSha256': menu['sha256'], 'freshFrameSha256': fresh['sha256'],
        'recheckCapturedAtUtc': fresh['capturedAtUtc'],
        'expiresAtUnix': approval['expiresAtUnix'],
        'bindingMatched': True, 'geometry': geometry, 'ocrConfidenceClaimed': False}
    save()
    return {'label': '開始出擊', 'nativeBounds': bounds,
            'nativePoint': [(left+right)//2, (top+bottom)//2],
            'basis': 'Root viewed this run fresh whole frame; same owned PID/window and visible text position rechecked'}

def launch():
    output = output_dir()
    assert os.environ['PROOF_PHASE'] == 'root_visible_start'
    assert not (output/'root-driver.json').exists()
    driver = Path(os.environ['GITHUB_WORKSPACE'])/'scripts/godot-android-swangle/observe.py'
    with (output/'root-driver.log').open('wb') as log:
        process = subprocess.Popen([sys.executable, str(driver)], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    write(output/'root-driver.json', {'pid': process.pid, 'startTicks': ticks(process.pid),
        'runId': os.environ['GITHUB_RUN_ID'], 'runAttempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'headSha': os.environ['GITHUB_SHA']})
    deadline = time.monotonic()+420
    while time.monotonic() < deadline:
        if (output/'root-visible-request.json').is_file():
            assert read(output/'native-observation.json')['status'] == 'WAIT_ROOT_FRESH_VISIBLE_APPROVAL'
            return
        if process.poll() is not None:
            raise RuntimeError('Owned native driver ended before fresh menu request')
        time.sleep(1)
    raise RuntimeError('Fresh-menu preparation deadline; cleanup step must stop owned driver')

def poll(release_id):
    output, request = output_dir(), read(output_dir()/'root-visible-request.json')
    assert release_id.isdigit()
    while time.time() < request['approvalDeadlineUnix']:
        assert same_process(request['driverPid'], request['driverStartTicks'])
        release = json.loads(gh(f'repos/{REPO}/releases/{release_id}'))
        assert release['id'] == int(release_id) and release['draft'] is True
        assert release['tag_name'] == APPROVAL_TAG and release['author']['login'] == 'mars-tw'
        candidates = [a for a in release['assets'] if a['name'] == request['approvalAssetName']]
        if len(candidates) > 1:
            raise RuntimeError('Multiple approvals; no continuation')
        if candidates:
            asset = candidates[0]
            assert asset['uploader']['login'] == 'mars-tw' and 0 < asset['size'] <= 16384
            raw = gh(f'repos/{REPO}/releases/assets/{asset["id"]}', True)
            assert len(raw) == asset['size']
            approval = json.loads(raw)
            assert all(approval.get(k) == request[k] for k in BINDINGS)
            write(output/'root-approval-api-receipt.json', {'method': 'GET', 'releaseId': int(release_id),
                'assetId': asset['id'], 'uploader': 'mars-tw', 'approvalSha256': hashlib.sha256(raw).hexdigest()})
            assert not (output/'root-start-approval.json').exists()
            pending = output/'root-start-approval.json.pending'
            pending.write_bytes(raw)
            pending.replace(output/'root-start-approval.json')
            return
        time.sleep(5)
    raise RuntimeError('Root approval absent at fixed deadline; no automatic new run')

def driver_identity_state(owned, proc_root=Path('/proc')):
    try:
        fields = (proc_root/str(owned['pid'])/'stat').read_text().rsplit(')', 1)[1].split()
    except FileNotFoundError:
        return 'DEAD'
    except (OSError, ValueError, IndexError, KeyError):
        return 'UNKNOWN_PROCESS_READ'
    if len(fields) <= 19:
        return 'UNKNOWN_PROCESS_READ'
    if fields[19] != owned['startTicks']:
        return 'UNKNOWN_PID_REUSED'
    return 'DEAD' if fields[0] == 'Z' else 'ALIVE'

def finish_hold(output, reason, owned=None, identity=None):
    write(output/'root-finish-observation.json', {'status': 'HOLD_COMPLETION_STOP',
        'reason': reason, 'ownedLedger': owned, 'driverIdentity': identity, 'noRetry': True})
    raise RuntimeError(reason)

def finish():
    output, deadline = output_dir(), time.monotonic()+240
    try:
        owned = read(output/'root-driver.json')
        expected = {'runId': os.environ['GITHUB_RUN_ID'],
                    'runAttempt': os.environ['GITHUB_RUN_ATTEMPT'], 'headSha': os.environ['GITHUB_SHA']}
        if not all(owned.get(k) == value for k, value in expected.items()):
            finish_hold(output, 'Owned completion ledger run binding differs', owned)
        if type(owned.get('pid')) is not int or owned['pid'] <= 0 or not isinstance(owned.get('startTicks'), str) or not owned['startTicks'].isdigit():
            finish_hold(output, 'Owned completion identity unavailable', owned)
    except (OSError, ValueError, KeyError) as error:
        finish_hold(output, 'Owned completion ledger unreadable: '+type(error).__name__)
    marker = output/'root-driver-finished.json'
    while time.monotonic() < deadline:
        identity = driver_identity_state(owned)
        if identity.startswith('UNKNOWN'):
            finish_hold(output, 'Owned driver identity unknown; no continuation', owned, identity)
        if marker.is_file():
            try:
                result = read(marker)
            except (OSError, ValueError) as error:
                finish_hold(output, 'Atomic completion marker unreadable: '+type(error).__name__, owned, identity)
            if result.get('schemaVersion') != 1 or not all(result.get(k) == value for k, value in expected.items()) or result.get('driverPid') != owned['pid'] or result.get('driverStartTicks') != owned['startTicks']:
                finish_hold(output, 'Completion marker differs from existing owned run', owned, identity)
            if result.get('status') != 'ROOT_VISIBLE_ONE_START_POST20_WARM90_REVIEW_PENDING':
                finish_hold(output, 'Native driver stopped; retain actual intent and frames', owned, identity)
            write(output/'root-finish-observation.json', {'status': 'OWNED_COMPLETION_MARKER_VERIFIED',
                'markerSha256': sha(marker), 'ownedLedger': owned, 'driverIdentity': identity,
                'runBindingVerified': True, 'noRetry': True})
            return
        if identity == 'DEAD':
            finish_hold(output, 'Owned driver exited without completion marker', owned, identity)
        time.sleep(1)
    finish_hold(output, 'Owned continuation deadline; no Start replay', owned)

def cleanup():
    output = output_dir()
    ledger = output/'root-driver.json'
    if not ledger.is_file():
        return
    owned = read(ledger)
    if same_process(owned['pid'], owned['startTicks']):
        os.kill(owned['pid'], signal.SIGTERM)
        deadline = time.monotonic()+5
        while same_process(owned['pid'], owned['startTicks']) and time.monotonic() < deadline:
            time.sleep(0.1)
        if same_process(owned['pid'], owned['startTicks']):
            os.kill(owned['pid'], signal.SIGKILL)
    # Driver's finally normally terminates its exact emulator child. For interrupted driver,
    # only the recorded native child with matching start ticks can be cleaned up here.
    report_file = output/'native-observation.json'
    if report_file.is_file():
        report = read(report_file)
        pid, identity = report.get('ownedEmulatorPid'), report.get('ownedEmulatorStartTicks')
        if pid and same_process(pid, identity):
            os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic()+5
            while same_process(pid, identity) and time.monotonic() < deadline:
                time.sleep(0.1)
            if same_process(pid, identity):
                os.kill(pid, signal.SIGKILL)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['launch', 'poll', 'finish', 'cleanup'])
    parser.add_argument('--approval-release-id')
    args = parser.parse_args()
    {'launch': launch, 'poll': lambda: poll(args.approval_release_id), 'finish': finish, 'cleanup': cleanup}[args.mode]()

if __name__ == '__main__':
    main()
