#!/usr/bin/env python3
"""Root-only neutral UIKit/XCTest probe, no Godot/signing/gameplay."""
import hashlib,importlib.util,json,os,re,shutil,subprocess,tempfile,plistlib,platform,threading,signal,time,select
from pathlib import Path
PIN='953c4206aa915d23b85315298bdb2e9ab0fab8c45ce9725ddc2f5fe2a4136b04'
ROOT=Path(os.environ['RUNNER_TEMP']).resolve();OUT=Path(os.environ['GITHUB_WORKSPACE'])/'output/crack-xctest-environment-probe'
work=Path(tempfile.mkdtemp(prefix='crack-xctest-environment-probe-',dir=ROOT));device=None
report={'status':'PREPARED_NOT_RUN','gameLaunched':False,'gameplayTested':False,'physicalDeviceTested':False,'storeQualified':False,'commands':[]}
def save():OUT.mkdir(parents=True,exist_ok=True);(OUT/'environment-probe.json').write_text(json.dumps(report,indent=2)+'\n')
def need(v,c):
 if not v:raise RuntimeError(c)
def safe(raw):
 rows=[s for s in raw.splitlines() if re.search(r'error:|failed|XCTDaemonErrorDomain|CRACK_ENV_|TEST EXECUTE|TEST SUCCEEDED',s,re.I)]
 return [re.sub(r'\/(?:Users|private|var|Volumes)/[^\s"<>]+','<path>',re.sub(r'https?://[^\s"<>]+','<url>',s))[:500] for s in rows[-25:]]
def cmd(label,args,seconds,allow=False):
 logfile=work/(str(len(report['commands'])+1)+'-'+label+'.log');flags={'timed':False,'truncated':False};proc=None
 def stop():
  if proc is not None and proc.poll() is None:
   try:
    if os.getpgid(proc.pid)==proc.pid:os.killpg(proc.pid,signal.SIGKILL)
   except ProcessLookupError:pass
 def expire():flags['timed']=True;stop()
 with logfile.open('xb') as log:
  proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True);deadline=time.monotonic()+seconds;timer=threading.Timer(seconds,expire);timer.start()
  try:
   count=0
   while True:
    remaining=deadline-time.monotonic()
    if remaining<=0:expire();break
    readable,_,_=select.select([proc.stdout],[],[],remaining)
    if not readable:expire();break
    data=os.read(proc.stdout.fileno(),65536)
    if not data:break
    if count+len(data)>20*1024*1024:flags['truncated']=True;stop();break
    log.write(data);count+=len(data)
   code=proc.wait(timeout=10)
  finally:
   timer.cancel();stop()
   if proc is not None:proc.wait(timeout=10)
 text=logfile.read_text(errors='replace')
 report['commands'].append({'label':label,'exitCode':code,'timedOut':flags['timed'],'outputBoundExceeded':flags['truncated'],'safeDiagnostics':safe(text),'rawLogPublished':False});save()
 need(not flags['truncated'],'OWN_LOG_BOUND')
 if not allow:need(code==0 and not flags['timed'],'OWN_COMMAND_FAILED_'+label.upper().replace('-','_'))
 return code,flags['timed'],text

try:
 report['hostPlatform']={'system':platform.system(),'machine':platform.machine()}
 need(platform.system()=='Darwin' and platform.machine()=='x86_64','ACTUAL_INTEL_MAC_REQUIRED')
 OUT.mkdir(parents=True,exist_ok=True);generator=ROOT/'crack-env-probe-input/create-crack-interaction-project.py';raw=generator.read_bytes()
 need(not generator.is_symlink() and hashlib.sha256(raw).hexdigest()==PIN,'GENERATOR_PIN_DIFFERS');report['generatorSha256']=PIN
 _,_,version=cmd('xcode-version',['xcodebuild','-version'],120);need(re.fullmatch(r'Xcode 26\.3\s+Build version 17C529\s*',version) is not None,'EXACT_XCODE_REQUIRED')
 spec=importlib.util.spec_from_file_location('owned_generator',generator);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 runner=work/'neutral-runner';module.generate(runner,'crackveil-vanguard','iphone')
 swift="""import XCTest
final class CaptureUITests: XCTestCase {
    @MainActor func testEnvironmentInitialization() throws {
        continueAfterFailure = false
        print("CRACK_ENV_METHOD_ENTERED")
        let app = XCUIApplication()
        app.launch()
        let foreground = app.state == .runningForeground
        print("CRACK_ENV_HOST_FOREGROUND=" + (foreground ? "true" : "false"))
        XCTAssertTrue(foreground, "OWN_CAPTUREHOST_NOT_FOREGROUND")
    }
}
"""
 (runner/'CaptureUITests.swift').write_text(swift);report['neutralSwiftSha256']=hashlib.sha256(swift.encode()).hexdigest()
 _,_,inventory=cmd('inventory',['xcrun','simctl','list','--json'],120);inventory=json.loads(inventory)
 runtimes=[x for x in inventory['runtimes'] if x.get('isAvailable') is True and not x.get('availabilityError') and re.fullmatch(r'26\.2(?:\.0)?',x.get('version','')) and re.fullmatch(r'com\.apple\.CoreSimulator\.SimRuntime\.iOS-26-2(?:-0)?',x.get('identifier',''))]
 models=[x for x in inventory['devicetypes'] if x.get('name')=='iPhone 17 Pro Max' and x.get('identifier','').startswith('com.apple.CoreSimulator.SimDeviceType.')]
 need(len(runtimes)==1 and len(models)==1,'EXACT_RUNTIME_MODEL_REQUIRED');runtime=runtimes[0];model=models[0]
 encoded=26*65536+2*256;need(model['minRuntimeVersion']<=encoded<=model['maxRuntimeVersion'],'MODEL_RUNTIME_INCOMPATIBLE')
 report.update({'xcode':'26.3/17C529','runtime':runtime['version'],'model':model['name'],'architecture':'x86_64','variablesRemoved':['game prelaunch','passive feed','manual Runner preinstall'],'variablesAreNotProvenCauses':True})
 derived=work/'derived-tests';cmd('runner-build',['xcodebuild','-project',str(runner/'Capture.xcodeproj'),'-scheme','Capture','-sdk','iphonesimulator','-destination','generic/platform=iOS Simulator','-derivedDataPath',str(derived),'CODE_SIGNING_ALLOWED=NO','ARCHS=x86_64','ONLY_ACTIVE_ARCH=YES','build-for-testing'],600)
 files=list((derived/'Build/Products').glob('*.xctestrun'));need(len(files)==1,'ONE_GENERATED_XCTESTRUN_REQUIRED')
 descriptor=files[0].read_bytes();need(len(descriptor)<=2*1024*1024,'XCTESTRUN_BOUND');value=plistlib.loads(descriptor);targets=[]
 def walk(x):
  if isinstance(x,list):
   for child in x:walk(child)
  elif isinstance(x,dict):
   if any(k in x for k in ['TestBundlePath','TestHostPath','UITargetAppPath']):targets.append(x)
   for child in x.values():
    if isinstance(child,(dict,list)):walk(child)
 walk(value);need(0<len(targets)<=20,'XCTESTRUN_TARGET_BOUND');records=[]
 for target in targets:
  record={}
  for key in ['BlueprintName','TestHostBundleIdentifier','UITargetAppBundleIdentifier','TargetApplicationBundleID']:
   if key in target:record[key]=target[key] if target[key] in ['tw.mars.capture.host','tw.mars.capture.tests','tw.mars.capture.tests.xctrunner','CaptureHost','CaptureUITests'] else '<unconfirmed>'
  for key in ['TestBundlePath','TestHostPath','UITargetAppPath']:
   if key in target:
    s=target[key];record[key]=s if isinstance(s,str) and re.fullmatch(r'__[A-Z_]+__/[A-Za-z0-9_./-]+',s) and '..' not in Path(s).parts else '<absolute-or-unknown-path-redacted>'
  records.append(record)
 shape=lambda x:{k:shape(v) for k,v in sorted(x.items())} if isinstance(x,dict) else [shape(v) for v in x] if isinstance(x,list) else type(x).__name__
 (OUT/'generated-xctestrun-summary.json').write_text(json.dumps({'sha256':hashlib.sha256(descriptor).hexdigest(),'bytes':len(descriptor),'schemaSha256':hashlib.sha256(json.dumps(shape(value),sort_keys=True).encode()).hexdigest(),'targets':records,'rawPathsPublished':False},indent=2)+'\n')
 previous={str(x.get('udid','')).lower() for group in inventory['devices'].values() for x in group};name='Mars-Crack-Environment-'+os.environ.get('GITHUB_RUN_ID','local')
 _,_,created=cmd('create',['xcrun','simctl','create',name,model['identifier'],runtime['identifier']],120);device=created.strip()
 need(re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}',device) and device.lower() not in previous,'FRESH_OWN_SIM_REQUIRED')
 def owned():
  _,_,text=cmd('confirm-own-device',['xcrun','simctl','list','--json'],120);now=json.loads(text)
  rows=[x for x in now.get('devices',{}).get(runtime['identifier'],[]) if str(x.get('udid','')).lower()==device.lower() and x.get('name')==name and x.get('deviceTypeIdentifier')==model['identifier'] and x.get('isAvailable') is True];need(len(rows)==1,'OWN_SIM_IDENTITY_UNCONFIRMED')
 owned();cmd('boot',['xcrun','simctl','boot',device],180);cmd('bootstatus',['xcrun','simctl','bootstatus',device,'-b'],600)
 code,timed,text=cmd('neutral-xctest',['xcodebuild','-project',str(runner/'Capture.xcodeproj'),'-scheme','Capture','-destination','platform=iOS Simulator,id='+device,'-derivedDataPath',str(derived),'-resultBundlePath',str(work/'neutral.xcresult'),'-parallel-testing-enabled','NO','CODE_SIGNING_ALLOWED=NO','ARCHS=x86_64','ONLY_ACTIVE_ARCH=YES','-only-testing:CaptureUITests/CaptureUITests/testEnvironmentInitialization','test-without-building'],1500,True)
 entered='CRACK_ENV_METHOD_ENTERED' in text;foreground='CRACK_ENV_HOST_FOREGROUND=true' in text
 report.update({'status':'NEUTRAL_HOST_INITIALIZATION_VERIFIED' if code==0 and not timed and entered and foreground else 'NEUTRAL_HOST_INITIALIZATION_UNCONFIRMED','methodEntered':entered,'hostForegroundConfirmed':foreground,'testExitCode':code,'testCommandTimedOut':timed,'axLoadedCode18Observed':bool(re.search(r'XCTDaemonErrorDomain Code=18',text)),'safeTestDiagnostics':safe(text)});save()
except Exception as e:
 code=str(e) if re.fullmatch('[A-Z0-9_]{1,100}',str(e)) else 'ENVIRONMENT_PROBE_UNKNOWN';report.update({'status':'PROBE_HOLD','safeReason':code});save()
finally:
 if device:
  try:owned();cmd('cleanup-shutdown',['xcrun','simctl','shutdown',device],60,True);cmd('cleanup-delete',['xcrun','simctl','delete',device],60);report['ownSimulatorDeleted']=True
  except Exception:report['ownSimulatorDeleted']=False
 target=work.resolve();need(target!=ROOT and target.is_relative_to(ROOT) and target.name.startswith('crack-xctest-environment-probe-'),'OWN_SCRATCH_REQUIRED');shutil.rmtree(target);report['scratchRemoved']=True;save()
print(json.dumps({k:report.get(k) for k in ['status','methodEntered','hostForegroundConfirmed','axLoadedCode18Observed','gameLaunched','gameplayTested','physicalDeviceTested','ownSimulatorDeleted']}))
raise SystemExit(0 if report.get('status')=='NEUTRAL_HOST_INITIALIZATION_VERIFIED' else 1)
