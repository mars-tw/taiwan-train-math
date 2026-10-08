"""Offline native OCR measurement only. No ADB, App, CI dispatch or store operations."""
import argparse
import csv
import hashlib
import io
import json
import os
import subprocess
import time
from pathlib import Path
try:
    import resource
except ImportError:
    resource = None

IMAGE_SHA = '6f954c557987e002ea9cc5672de31654c146861b0ddfd8ddf2e3fc0e028ac947'
MODEL_SHA = '529c5b5797d64b126065cd55f2bb4c7fd7b15790798091b1ff259941a829330b'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def error_record(error):
    return {'type': type(error).__name__, 'message': str(error)}

def read_proc_status(pid):
    try:
        return (Path('/proc')/str(pid)/'status').read_text().splitlines()
    except OSError:
        return []

def read_words(tsv):
    rows = csv.DictReader(io.StringIO(tsv.read_text(encoding='utf-8', errors='replace')), delimiter='\t')
    return [{'text': r.get('text', ''), 'confidence': r.get('conf'),
             'left': r.get('left'), 'top': r.get('top'), 'width': r.get('width'), 'height': r.get('height')}
            for r in rows if (r.get('text') or '').strip()]

def run_trial(argv, child_env, deadline, label, output, status_reader=read_proc_status):
    tsv, errors = output/(label+'.tsv'), output/(label+'.stderr')
    trial = {'label': label, 'childOmpThreadLimit': child_env.get('OMP_THREAD_LIMIT'),
             'childOmpNumThreads': child_env.get('OMP_NUM_THREADS'), 'deadlineSeconds': deadline,
             'timedOut': False, 'observerError': None, 'resultReadError': None,
             'cleanup': {'ownPid': None, 'killRequested': False, 'waitCompleted': False,
                         'outcomeUnknown': False, 'errors': []}}
    process, child_started, child_finished = None, None, None
    cpu_before = resource.getrusage(resource.RUSAGE_CHILDREN) if resource else None
    peak_threads, peak_rss_kb = 0, 0
    try:
        with tsv.open('wb') as stdout, errors.open('wb') as stderr:
            child_started = time.monotonic()
            process = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=child_env)
            trial['cleanup']['ownPid'] = process.pid
            while process.poll() is None:
                for line in status_reader(process.pid):
                    if line.startswith('Threads:'):
                        peak_threads = max(peak_threads, int(line.split()[1]))
                    elif line.startswith('VmRSS:'):
                        peak_rss_kb = max(peak_rss_kb, int(line.split()[1]))
                if time.monotonic()-child_started > deadline:
                    trial['timedOut'] = True
                    break
                time.sleep(0.05)
    except BaseException as error:
        trial['observerError'] = error_record(error)
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    trial['cleanup']['killRequested'] = True
                    process.kill()
            except BaseException as error:
                trial['cleanup']['errors'].append(error_record(error))
            try:
                process.wait(timeout=5)
                child_finished = time.monotonic()
                trial['cleanup']['waitCompleted'] = True
            except BaseException as error:
                trial['cleanup']['errors'].append(error_record(error))
                trial['cleanup']['outcomeUnknown'] = True
        trial['returnCode'] = process.returncode if process is not None else None
        trial['durationSeconds'] = child_finished-child_started if child_finished is not None else None
        trial['childFinishedMonotonic'] = child_finished
        trial['peakObservedThreads'] = peak_threads or None
        trial['peakObservedRssKb'] = peak_rss_kb or None
        cpu_after = resource.getrusage(resource.RUSAGE_CHILDREN) if resource else None
        trial['childUserCpuSeconds'] = cpu_after.ru_utime-cpu_before.ru_utime if cpu_after else None
        trial['childSystemCpuSeconds'] = cpu_after.ru_stime-cpu_before.ru_stime if cpu_after else None
        trial['tsvSha256'], trial['tsvBytes'], trial['words'] = None, None, []
        try:
            if tsv.is_file():
                trial['tsvSha256'], trial['tsvBytes'] = sha(tsv), tsv.stat().st_size
                trial['words'] = read_words(tsv)
            if errors.is_file():
                trial['stderrSha256'], trial['stderrBytes'] = sha(errors), errors.stat().st_size
        except BaseException as error:
            trial['resultReadError'] = error_record(error)
        trial['stopWithoutNextTrial'] = bool(trial['observerError'] or trial['resultReadError'] or
            trial['cleanup']['errors'] or trial['cleanup']['outcomeUnknown'] or process is None or
            (trial['returnCode'] != 0 and not trial['timedOut']))
        (output/(label+'.receipt.json')).write_text(json.dumps(trial, ensure_ascii=True, indent=2)+'\n', encoding='utf-8')
    return trial

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--tesseract', type=Path, required=True)
    parser.add_argument('--tessdata', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert args.image.is_file() and sha(args.image) == IMAGE_SHA
    assert args.tesseract.is_file()
    assert sha(args.tessdata/'chi_tra.traineddata') == MODEL_SHA
    version = subprocess.run([str(args.tesseract), '--version'], capture_output=True, timeout=10, check=True)
    version_text = (version.stdout + version.stderr).decode('utf-8', 'replace')
    assert 'tesseract 5.3.4' in version_text
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'scope': 'Offline OCR only', 'imageSha256': IMAGE_SHA,
              'nativeTesseractBinarySha256': sha(args.tesseract), 'version': version_text,
              'chiTraSha256': MODEL_SHA, 'engSha256': sha(args.tessdata/'eng.traineddata'),
              'imagePreprocessed': False, 'nativeAppStarted': False,
              'logicalCpuCount': os.cpu_count(),
              'cpuAffinity': sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
              'measurements': []}
    for label, limit, deadline in [('default-threads', None, 30), ('omp-one', '1', 60)]:
        child_env = os.environ.copy()
        child_env.pop('OMP_THREAD_LIMIT', None)
        if limit is not None:
            child_env['OMP_THREAD_LIMIT'] = limit
        argv = [str(args.tesseract), str(args.image), 'stdout', '--tessdata-dir',
                str(args.tessdata), '-l', 'chi_tra+eng', '--oem', '1', '--psm', '11', 'tsv']
        trial = run_trial(argv, child_env, deadline, label, args.output)
        report['measurements'].append(trial)
        (args.output/'measurement.json').write_text(json.dumps(report, ensure_ascii=True, indent=2)+'\n', encoding='utf-8')
        if trial['stopWithoutNextTrial']:
            raise RuntimeError('OCR diagnostic observer/cleanup/result stopped; no next trial or retry')
    print(json.dumps({'status': 'EXECUTED_OFFLINE_OCR_MEASUREMENT', 'output': str(args.output)}, ensure_ascii=True))

if __name__ == '__main__':
    main()
