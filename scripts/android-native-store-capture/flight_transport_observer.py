"""Flight-only diagnostics inside the exact fresh owned GitHub CI VM. No resource tuning."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime,timezone

PROJECT='island-flight-school';PACKAGE='tw.mars.islandflightschool'
def now():return datetime.now(timezone.utc).isoformat()
def sha(raw):return hashlib.sha256(raw).hexdigest()

class FlightTransportObserver:
 def __init__(self,out,sdk,adb,serial,avd,run_id,apk):
  if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!='mars-tw/taiwan-train-math':
   raise RuntimeError('Flight observation is restricted to owned CI')
  if not run_id.isdigit() or avd!='NativeCapturePhone_'+run_id+'_'+PROJECT or serial!='emulator-5554':
   raise RuntimeError('Exact Flight phone run/AVD/serial required')
  self.directory=Path(out)/'flight-transport-diagnostics';self.directory.mkdir(exist_ok=True)
  self.sdk,self.adb,self.serial,self.avd=Path(sdk).resolve(),adb,serial,avd
  self.log_process=None;self.log_stream=None;self.started=time.monotonic()
  self.report={'projectId':PROJECT,'packageName':PACKAGE,'avd':avd,'runId':run_id,'serial':serial,
   'observedAtUtc':now(),'apkSha256':sha(Path(apk).read_bytes()),'firstNativeFailure':None,
   'ownEmulator':None,'snapshots':[],'ownAppPid':None,'continuousPidLogStarted':False,
   'gameCrashOrOomClaimed':False,'resourceTuningPerformed':False}
  self.find_exact_ci_emulator();self.snapshot('before_install_or_launch');self.save()
 def save(self):
  (self.directory/'transport-observation.json').write_text(json.dumps(self.report,indent=2)+'\n',encoding='utf-8')
 def find_exact_ci_emulator(self):
  # Only /proc of this disposable Linux CI VM. Do not query AVD/user inventory
  # or record unrelated processes; require exact -avd pair and SDK executable.
  matches=[]
  for entry in Path('/proc').iterdir():
   if not entry.name.isdigit():continue
   try:
    args=(entry/'cmdline').read_bytes().split(b'\0');args=[x.decode('utf-8','strict') for x in args if x]
    if not args or '-avd' not in args:continue
    index=args.index('-avd')
    if index+1>=len(args) or args[index+1]!=self.avd:continue
    executable=Path(args[0]).resolve()
    if not executable.is_relative_to(self.sdk/'emulator') or not (executable.name=='emulator' or executable.name.startswith('qemu-system-')):continue
    stat=(entry/'stat').read_text().rsplit(')',1)[1].split();matches.append({'pid':int(entry.name),'executable':str(executable),'avd':self.avd,'startTicks':int(stat[19])})
   except (OSError,UnicodeError,ValueError,IndexError):continue
  if len(matches)==1:self.report['ownEmulator']=matches[0]
  else:self.report['ownEmulatorIdentityUnknown']={'exactMatches':len(matches),'noFallbackOrOtherProcessAccepted':True}
 def snapshot(self,phase):
  row={'phase':phase,'observedAtUtc':now(),'elapsedSeconds':time.monotonic()-self.started,'emulatorExitSignalUnknown':True}
  try:
   mem={};allowed={'MemTotal','MemAvailable','MemFree','Buffers','Cached','SwapTotal','SwapFree'}
   for line in Path('/proc/meminfo').read_text().splitlines():
    key,value=line.split(':',1)
    if key in allowed:mem[key]=value.strip()
   row['vmMemory']=mem;row['vmCpuJiffies']=Path('/proc/stat').read_text().splitlines()[0]
   own=self.report.get('ownEmulator')
   if own:
    path=Path('/proc')/str(own['pid']);stat=(path/'stat').read_text().rsplit(')',1)[1].split()
    if int(stat[19])!=own['startTicks']:raise RuntimeError('PID reused; no metrics attributed')
    row['ownEmulatorAlive']=True;row['ownEmulatorState']=stat[0];row['ownEmulatorCpuTicks']={'user':int(stat[11]),'system':int(stat[12])}
    row['ownEmulatorRuntimeSeconds']=float(Path('/proc/uptime').read_text().split()[0])-own['startTicks']/os.sysconf('SC_CLK_TCK')
    row['ownEmulatorMemory']={key:value.strip() for key,value in (x.split(':',1) for x in (path/'status').read_text().splitlines() if ':' in x) if key in {'VmRSS','VmHWM','VmSize','VmPeak','Threads'}}
   else:row['ownEmulatorAlive']=None
  except (OSError,ValueError,RuntimeError,IndexError) as error:
   row['observationError']=type(error).__name__;row['ownEmulatorAlive']=False if self.report.get('ownEmulator') else None
  if self.log_process is not None:row['ownPidLogProcessExitCode']=self.log_process.poll()
  self.report['snapshots'].append(row);self.save()
 def record_command(self,args,code,stdout,stderr,timedout):
  # Process exit0 is insufficient: preserve empty/non-PNG first payload before
  # original capture decoding rejects it. Never manufacture/retry a frame.
  if args==('exec-out','screencap','-p') and code==0 and not timedout and not stdout.startswith(b'\x89PNG\r\n\x1a\n') and not self.report.get('firstInvalidNativePng'):
   out=self.directory/'first-invalid-native-png.stdout.bin';err=self.directory/'first-invalid-native-png.stderr.bin'
   out.write_bytes(stdout);err.write_bytes(stderr)
   self.report['firstInvalidNativePng']={'command':list(args),'exitCode':code,'timedOut':False,'observedAtUtc':now(),
    'stdoutFile':out.name,'stderrFile':err.name,'stdoutBytes':len(stdout),'stderrBytes':len(stderr),
    'stdoutSha256':sha(stdout),'stderrSha256':sha(stderr),'invalidPngSignatureOrEmpty':True,'notAReadyGameFrame':True}
   self.snapshot('first_invalid_native_png_payload');self.save()
  # Commands originate only in the fixed capture driver using owned adb -s.
  # Preserve the first actual failure; later failures never overwrite it.
  if (code==0 and not timedout) or self.report['firstNativeFailure'] is not None:return
  stdout_file=self.directory/'first-failure.stdout.bin';stderr_file=self.directory/'first-failure.stderr.bin'
  stdout_file.write_bytes(stdout);stderr_file.write_bytes(stderr)
  self.report['firstNativeFailure']={'command':list(args),'exitCode':code,'timedOut':timedout,'observedAtUtc':now(),
   'stdoutFile':stdout_file.name,'stderrFile':stderr_file.name,'stdoutBytes':len(stdout),'stderrBytes':len(stderr),
   'stdoutSha256':sha(stdout),'stderrSha256':sha(stderr),'outcomeOrRootCauseNotInferred':True}
  self.snapshot('first_native_command_failure')
  try:
   state=subprocess.run([self.adb,'-s',self.serial,'get-state'],capture_output=True,timeout=5)
   (self.directory/'failure-get-state.stdout.bin').write_bytes(state.stdout);(self.directory/'failure-get-state.stderr.bin').write_bytes(state.stderr)
   self.report['failureTransportReadback']={'exitCode':state.returncode,'stdoutSha256':sha(state.stdout),'stderrSha256':sha(state.stderr),'observedAtUtc':now()}
  except (OSError,subprocess.TimeoutExpired):self.report['failureTransportReadback']={'unknown':True,'observedAtUtc':now()}
  self.save()
 def after_launch(self):
  self.snapshot('after_signed_own_app_launch_before_readiness')
  try:
   reply=subprocess.run([self.adb,'-s',self.serial,'shell','pidof',PACKAGE],capture_output=True,timeout=5)
   raw=reply.stdout.decode('ascii','strict').strip()
   if reply.returncode!=0 or not raw.isdigit():raise RuntimeError('Own App PID not uniquely observed')
   pid=int(raw);self.report['ownAppPid']=pid
   file=self.directory/'own-app-pid-continuous.log';self.log_stream=file.open('wb')
   self.log_process=subprocess.Popen([self.adb,'-s',self.serial,'logcat','--pid='+str(pid),'-v','threadtime'],stdout=self.log_stream,stderr=subprocess.STDOUT)
   self.report.update(continuousPidLogStarted=True,continuousPidLogFile=file.name,continuousPidLogStartedAtUtc=now(),logFilter='exact own-app PID only')
  except subprocess.TimeoutExpired as error:
   # Diagnostic PID readiness is not a new primary App readiness prerequisite.
   stdout=error.stdout or b'';stderr=error.stderr or b''
   (self.directory/'own-pid-timeout.stdout.bin').write_bytes(stdout)
   (self.directory/'own-pid-timeout.stderr.bin').write_bytes(stderr)
   self.report.update(continuousPidLogStartUnknown=True,continuousPidLogStarted=False,
    ownPidObservation={'command':['shell','pidof',PACKAGE],'timedOut':True,'timeoutSeconds':5,
     'exitCode':None,'observedAtUtc':now(),'stdoutBytes':len(stdout),'stderrBytes':len(stderr),
     'stdoutSha256':sha(stdout),'stderrSha256':sha(stderr),'ownAppPidUnknown':True,
     'originalPrimaryReadinessMayContinue':True})
  except (OSError,UnicodeError,RuntimeError):self.report['continuousPidLogStartUnknown']=True
  self.save()
 def finish(self):
  self.snapshot('capture_finally_before_existing_log_fallback')
  if self.log_process is not None:
   # This is our returned logcat child only, never the emulator or other PID.
   if self.log_process.poll() is None:
    self.log_process.terminate()
    try:self.log_process.wait(timeout=5)
    except subprocess.TimeoutExpired:self.log_process.kill();self.log_process.wait(timeout=5)
   self.report['ownedLogcatChildExitCode']=self.log_process.returncode
  if self.log_stream is not None:self.log_stream.close()
  file=self.directory/'own-app-pid-continuous.log'
  if file.exists():self.report.update(continuousPidLogBytes=file.stat().st_size,continuousPidLogSha256=sha(file.read_bytes()))
  self.report['finishedAtUtc']=now();self.save()
