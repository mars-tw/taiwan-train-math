"""One owned Simulator log-sink capability probe; no Appium/sign/store actions."""
from pathlib import Path
import argparse,datetime,hashlib,json,math,os,platform,re,selectors,shutil,signal,subprocess,sys,tempfile,time,uuid
APP='tw.mars.sevendistrictreckoning';PCK='0fd586eb8e4f0b40ea0b7b88b0a1f7b3425ece3dfe34c59cf9418d578ad98bd7'
MAX_BYTES=2*1024*1024;MAX_JSON=4096;MAX_RECORDS=64
PHASES={'first_frame','base_world','actors','district_life','content_world','urban_detail','contacts','expansion','taiwan_world','bindings','world_ready'}
EVENTS={'begin','phase','complete','first_frame_wait','first_frame_drawn','first_frame_headless_not_rendered','font_load_begin','font_load_end'}
class ProbeStop(Exception):pass
def require(value,code):
 if not value:raise ProbeStop(code)
def inside(path,parent):return path.resolve()!=parent.resolve() and path.resolve().is_relative_to(parent.resolve())
def manual_field_evidence(manual):
 require(isinstance(manual,str) and len(manual)<=131072,'MANUAL_PREDICATE_FIELDS_UNVERIFIED')
 fields=('processID','subsystem','category','eventMessage','messageType')
 raw={field:bool(re.search(r'\b'+field+r'\b',manual)) for field in fields}
 # SGR is presentation-only. Leave other/unknown escape sequences intact,
 # rather than guessing cursor operations or joining field-name fragments.
 ansi=re.compile(r'\x1b\[[0-9:;]*m');controls=len(ansi.findall(manual));text=ansi.sub('',manual)
 # Only BS/CR/LF/TAB have modeled display semantics. Unknown controls may
 # leave all field tokens present, so preserve their safe counts and refuse trust.
 unknown={'ESC':0,'C0':0,'DEL':0}
 for char in text:
  value=ord(char)
  if value==27:unknown['ESC']+=1
  elif value==127:unknown['DEL']+=1
  elif value<32 and value not in {8,9,10,13}:unknown['C0']+=1
 rendered=[]
 for line in text.split('\n'):
  cells=[];cursor=0
  for char in line:
   if char=='\b':cursor=max(0,cursor-1)
   elif char=='\r':cursor=0
   else:
    if cursor<len(cells):cells[cursor]=char
    else:cells.append(char)
    cursor+=1
  rendered.append(''.join(cells))
 normalized='\n'.join(rendered)
 present={field:bool(re.search(r'\b'+field+r'\b',normalized)) for field in fields}
 return {'rawFieldPresence':raw,'normalizedFieldPresence':present,'missingFields':[field for field in fields if not present[field]],'backspaceCount':manual.count('\b'),'ansiControlCount':controls,'unknownControlCount':sum(unknown.values()),'unknownControlKinds':[kind for kind,count in unknown.items() if count]}

def capabilities(helps):
 stream=helps.get('log-stream-help','');show=helps.get('log-show-help','');manual=helps.get('log-manual','')
 evidence=manual_field_evidence(manual)
 return {'streamInfoNdjson':all(key in stream for key in ['--predicate','--style','ndjson','--level','info']),
  'showInfoNdjson':all(key in show for key in ['--predicate','--style','ndjson','--info','--last']),
  'exactPredicateFields':evidence['unknownControlCount']==0 and all(evidence['normalizedFieldPresence'].values())}
def log_help_response(label,payload,stats):
 require(label in {'log-stream-help','log-show-help'},'HELP_RESPONSE_UNRECOGNIZED')
 require(type(stats.get('exitCode')) is int and stats['exitCode'] in {0,64} and stats.get('timedOut') is False and stats.get('bytesDropped')==0 and 0<len(payload)<=131072 and payload.strip(),'HELP_RESPONSE_UNRECOGNIZED')
 try:text=payload.decode('utf-8')
 except UnicodeError:raise ProbeStop('HELP_RESPONSE_UNRECOGNIZED')
 verb='stream' if label=='log-stream-help' else 'show'
 require(re.search(r'(?im)^\s*usage:\s*(?:/usr/bin/)?log\s+'+verb+r'\b',text),'HELP_RESPONSE_UNRECOGNIZED')
 return text

def parse_pid(text):
 rows=re.findall(r'^'+re.escape(APP)+r':\s*([1-9][0-9]*)\s*$',text,re.M)
 require(len(rows)==1,'OWNED_APP_PID_NOT_UNAMBIGUOUS');return int(rows[0])
def typed_marker(message):
 if not isinstance(message,str) or len(message)>512 or not message.startswith('SEVEN_STARTUP '):return None
 try:v=json.loads(message[14:])
 except (ValueError,TypeError):return None
 if not isinstance(v,dict) or set(v)!={'event','phase','elapsed_ms','items','ready'} or type(v['event']) is not str or type(v['phase']) is not str or v['event'] not in EVENTS or v['phase'] not in PHASES:return None
 try:valid=type(v['elapsed_ms']) in [int,float] and math.isfinite(v['elapsed_ms']) and v['elapsed_ms']>=0
 except (OverflowError,ValueError,TypeError):valid=False
 if not valid or type(v['items']) is not int or not 0<=v['items']<=9007199254740991 or type(v['ready']) is not bool:return None
 return {k:v[k] for k in ['event','phase','elapsed_ms','items','ready']}
def parse_unified(payload,pid):
 require(len(payload)<=MAX_BYTES and type(pid) is int and pid>0,'LOG_INPUT_OR_PID_BOUND')
 values=[];counts={'rowsReceived':0,'knownSchemaRows':0,'exactScopeRows':0,'typedAccepted':0,'typedRejected':0,'recordLimitDropped':0};schema={'processID':int,'subsystem':str,'category':str,'messageType':str,'eventMessage':str}
 try:text=payload.decode('utf-8')
 except UnicodeError:raise ProbeStop('LOG_JSON_UTF8_UNRECOGNIZED')
 for line in text.splitlines():
  if not line.strip():continue
  require(len(line.encode())<=MAX_JSON,'LOG_JSON_RECORD_BOUND');counts['rowsReceived']+=1
  try:row=json.loads(line)
  except ValueError:raise ProbeStop('LOG_JSON_SCHEMA_UNRECOGNIZED')
  require(isinstance(row,dict) and all(type(row.get(k)) is t for k,t in schema.items()),'LOG_JSON_SCHEMA_UNRECOGNIZED');counts['knownSchemaRows']+=1
  if row['processID']!=pid or row['subsystem']!=APP or row['category']!='engine' or row['messageType']!='Info':continue
  counts['exactScopeRows']+=1;v=typed_marker(row['eventMessage'])
  if v is None:counts['typedRejected']+=1;continue
  if len(values)<MAX_RECORDS:values.append(v);counts['typedAccepted']+=1
  else:counts['recordLimitDropped']+=1
 return values,counts
def owned_identity(inventory,udid,name,runtime,model):
 rows=[d for d in inventory.get('devices',{}).get(runtime,[]) if d.get('udid','').lower()==udid.lower()]
 return len(rows)==1 and rows[0].get('name')==name and rows[0].get('deviceTypeIdentifier')==model and rows[0].get('isAvailable') is True
def safe_file(data_container,udid):
 container=Path(data_container);require(container.is_absolute() and udid.lower() in [x.lower() for x in container.parts],'OWNED_CONTAINER_PATH_UNCONFIRMED')
 root=container.resolve();file=container/'Documents/logs/godot.log'
 require(all(not p.is_symlink() for p in [container,container/'Documents',container/'Documents/logs',file]) and inside(file,root),'CANONICAL_LOG_PATH_UNCONFIRMED')
 return file
def run_probe(source,metadata,verifier,output):
 require(platform.system()=='Darwin' and platform.machine()=='x86_64' and os.environ.get('RUNNER_TEMP'),'EXACT_INTEL_MAC_REQUIRED')
 root=Path(os.environ['RUNNER_TEMP']).resolve();work=Path(os.environ['GITHUB_WORKSPACE']).resolve()
 source=Path(source).resolve();metadata=Path(metadata).resolve();verifier=Path(verifier).resolve();output=Path(output).resolve()
 require(inside(source,root) and inside(metadata,root) and inside(verifier,root) and inside(output,work) and not output.exists(),'FRESH_OWNED_INPUT_OUTPUT_REQUIRED')
 output.mkdir(parents=True);scratch=Path(tempfile.mkdtemp(prefix='seven-log-sink-',dir=root));os.chmod(scratch,0o700)
 report={'status':'RUNNING_CAPABILITY_PROBE','appId':APP,'build':4,'sourcePckModified':False,'actualCapabilitiesVerified':False,'phaseEvents':[],'coverage':{},'commands':[],'cleanup':[],'nativeRuntimeReady':False,'uiReleaseReady':False,'physicalDeviceTested':False,'rawLogsPublished':False,'pidOrPrivatePathPublished':False,'signerSecretsUsed':False,'storeMutation':False}
 children=set();owner=None;sequence=0;environment={k:v for k,v in os.environ.items() if not re.search('PASSWORD|TOKEN|P12|PRIVATE|SECRET',k,re.I)}
 def publish():
  temp=output/'capability.pending';temp.write_text(json.dumps(report,indent=2)+'\n');os.replace(temp,output/'capability.json')
 def command(label,args,seconds=15,limit=131072,allow_failure=False,stdout_only=False):
  nonlocal sequence
  sequence+=1;report['activeCommand']={'label':label,'startedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()};publish()
  process=subprocess.Popen([str(x) for x in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment,cwd=scratch,start_new_session=True);children.add(process)
  selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ);selector.register(process.stderr,selectors.EVENT_READ)
  received=0;retained=bytearray();stdout=bytearray();start=time.monotonic();timed_out=False
  while selector.get_map():
   if time.monotonic()-start>seconds and process.poll() is None:timed_out=True;os.killpg(process.pid,signal.SIGTERM)
   if time.monotonic()-start>seconds+5 and process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
   if time.monotonic()-start>seconds+10:break
   for key,_ in selector.select(.1):
    block=os.read(key.fileobj.fileno(),65536)
    if not block:selector.unregister(key.fileobj);continue
    received+=len(block);remaining=max(0,limit-len(retained));keep=block[:remaining];retained.extend(keep)
    if key.fileobj is process.stdout:stdout.extend(keep)
  code=process.wait(timeout=5);selector.close();children.discard(process)
  private=scratch/(str(sequence)+'-'+label+'.log');private.write_bytes(retained)
  row={'command':label,'configuredBudgetSeconds':seconds,'elapsedMs':round((time.monotonic()-start)*1000),'exitCode':code,'exitSignal':signal.Signals(-code).name if code<0 else None,'timedOut':timed_out,'bytesReceived':received,'bytesRetained':len(retained),'bytesDropped':received-len(retained)};report['commands'].append(row);report.pop('activeCommand',None);publish()
  if not allow_failure:require(code==0 and not timed_out,'COMMAND_FAILED_'+label.upper())
  return bytes(stdout if stdout_only else retained),row
 def json_command(label,args,seconds=15):return json.loads(command(label,args,seconds=seconds,limit=MAX_BYTES)[0])
 def confirm():
  require(owner and owned_identity(json_command('own-inventory',['xcrun','simctl','list','--json']),**owner),'OWNED_SIM_IDENTITY_UNCONFIRMED')
 try:
  report['toolPreflight']={'simctlFound':False,'xcodeVersionExact':False,'supportState':'UNKNOWN'}
  raw,find_stats=command('tool-find-simctl',['xcrun','--find','simctl'],seconds=90)
  found=raw.decode('utf-8','replace').strip();require(len(found.splitlines())==1 and Path(found).is_absolute() and Path(found).name=='simctl','SIMCTL_TOOL_FIND_UNCONFIRMED')
  report['toolPreflight'].update(simctlFound=True,findElapsedMs=find_stats['elapsedMs']);publish()
  raw,xcode_stats=command('tool-xcode-version',['xcodebuild','-version'],seconds=90)
  require(re.fullmatch(r'Xcode 26\.3\s+Build version 17C529\s*',raw.decode().strip()),'EXACT_XCODE_REQUIRED')
  report['toolPreflight'].update(xcodeVersionExact=True,xcodeElapsedMs=xcode_stats['elapsedMs']);publish()
  report['simctlLifecyclePriorEvidence']={'status': 'SIMCTL_LIFECYCLE_PRIOR_ACTUAL_VERIFIED', 'evidenceRunIds': [37732463543, 37726700215, 37716545483], 'evidenceReceiptSha256': ['a86758376fb5688274783cdf652c611b511869cca1ca6ddbcc690e56dcf9d773', 'eb583a44167dbb183b87b8a57cf75484b4fa30466bbf887378d261245f0def68', '562fa19db9fe5610a999d22f666e37a008587236dd7ac50ad8549412d9e836f1'], 'observerSha256': 'e9cb3c219d5e2ff78b98a034e076a8a0209902afd5721de376d3c1db79edfccb', 'verifiedCommandTypes': ['list', 'create', 'boot', 'bootstatus', 'install', 'launch', 'io', 'delete'], 'notObservedInReferencedReceipts': ['terminate', 'get_app_container', 'shutdown', 'spawn'], 'currentHelpProbed': False, 'specificCommandPolicyUnchanged': True, 'freshOwnerIdentityRequired': True};publish()
  helps={}
  help_commands=[('log-stream-help',['/usr/bin/log','help','stream']),('log-show-help',['/usr/bin/log','help','show']),('log-manual',['/usr/bin/man','log'])]
  environment['MANPAGER']='cat';environment['PAGER']='cat'
  for label,args in help_commands:
   usage_help=label in {'log-stream-help','log-show-help'}
   raw,stats=command(label,args,seconds=15,allow_failure=usage_help)
   helps[label]=log_help_response(label,raw,stats) if usage_help else raw.decode('utf-8','replace')
  report['manualPredicateFieldEvidence']=manual_field_evidence(helps.get('log-manual',''))
  support=capabilities(helps);report['helpCapabilities']=support;publish()
  require(support['streamInfoNdjson'] and support['showInfoNdjson'],'CAPABILITY_UNSUPPORTED_HELP_OR_PREDICATE')
  require(support['exactPredicateFields'],'MANUAL_PREDICATE_FIELDS_UNVERIFIED')
  command('source-verify',[sys.executable,verifier,'source','--root',source,'--metadata',metadata,'--project','seven-district-reckoning','--output',output/'source-verification.json'],seconds=300,limit=MAX_BYTES)
  original_pck=hashlib.sha256((source/'SevenDistrict.pck').read_bytes()).hexdigest();require(original_pck==PCK,'ORIGINAL_PCK4_REQUIRED')
  derived=scratch/'derived-sim'
  command('sim-build',['xcodebuild','-project',source/'SevenDistrict.xcodeproj','-scheme','SevenDistrict','-configuration','Debug','-sdk','iphonesimulator','-destination','generic/platform=iOS Simulator','-derivedDataPath',derived,'CODE_SIGNING_ALLOWED=NO','ONLY_ACTIVE_ARCH=NO','ARCHS=x86_64','EXCLUDED_ARCHS=arm64','build'],seconds=2400,limit=MAX_BYTES)
  app=derived/'Build/Products/Debug-iphonesimulator/SevenDistrict.app'
  command('sim-verify',[sys.executable,verifier,'app','--root',source,'--project','seven-district-reckoning','--app',app,'--output',output/'simulator-verification.json'],seconds=300,limit=MAX_BYTES)
  command('source-after-link',[sys.executable,verifier,'source','--root',source,'--metadata',metadata,'--project','seven-district-reckoning','--output',output/'source-verification-after-link.json'],seconds=300,limit=MAX_BYTES)
  inventory=json_command('inventory',['xcrun','simctl','list','--json']);old={d['udid'].lower() for rows in inventory['devices'].values() for d in rows}
  runtimes=[r for r in inventory['runtimes'] if r.get('isAvailable') and r['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-') and r['version'].split('.')[0]=='26'];runtimes.sort(key=lambda r:tuple(map(int,r['version'].split('.'))),reverse=True)
  models=[d for d in inventory['devicetypes'] if d['name']=='iPhone 17 Pro Max'];require(runtimes and len(models)==1,'OWNED_MODEL_RUNTIME_UNAVAILABLE')
  name='Mars-Seven-Log-'+uuid.uuid4().hex;raw,_=command('create',['xcrun','simctl','create',name,models[0]['identifier'],runtimes[0]['identifier']]);udid=raw.decode().strip();require(re.fullmatch(r'[A-Fa-f0-9]{8}(?:-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}',udid) and udid.lower() not in old,'FRESH_OWNED_UDID_REQUIRED')
  owner={'udid':udid,'name':name,'runtime':runtimes[0]['identifier'],'model':models[0]['identifier']};confirm()
  command('boot',['xcrun','simctl','boot',udid],seconds=180);command('bootstatus',['xcrun','simctl','bootstatus',udid,'-b'],seconds=600);confirm()
  command('install',['xcrun','simctl','install',udid,app],seconds=360);raw,_=command('launch',['xcrun','simctl','launch',udid,APP],seconds=360);pid=parse_pid(raw.decode('utf-8','replace'));os.kill(pid,0);report['ownedAppPidConfirmed']=True
  predicate=f'processID == {pid} AND subsystem == "{APP}" AND category == "engine" AND messageType == 1 AND eventMessage BEGINSWITH "SEVEN_STARTUP "'
  raw,stats=command('owned-info-stream',['/usr/bin/log','stream','--level','info','--style','ndjson','--predicate',predicate],seconds=60,limit=MAX_BYTES,allow_failure=True,stdout_only=True)
  require(stats['timedOut'] or stats['exitCode']==0,'CAPABILITY_LOG_STREAM_REJECTED')
  raw_values,counts=parse_unified(raw,pid)
  values=[]
  for value in raw_values:
   if value not in values and len(values)<MAX_RECORDS:values.append(value)
  # One predeclared, supported same-PID query covers early launch markers if INFO
  # was persisted; this is not an alternate-argument retry of a rejected command.
  history,history_stats=command('owned-info-history',['/usr/bin/log','show','--last','2m','--info','--style','ndjson','--predicate',predicate],seconds=30,limit=MAX_BYTES,stdout_only=True)
  early,early_counts=parse_unified(history,pid);require(counts['knownSchemaRows']+early_counts['knownSchemaRows']>0,'CAPABILITY_JSON_SCHEMA_NOT_OBSERVED')
  for value in early:
   if value not in values and len(values)<MAX_RECORDS:values.append(value)
  report['earlyHistoryCoverage']=early_counts;report['earlyInfoPersistenceNotGuaranteed']=True
  report.update(actualCapabilitiesVerified=True,phaseEvents=values,coverage={**counts,**{k:stats[k] for k in ['bytesReceived','bytesRetained','bytesDropped']}},evidenceStatus='TYPED_PHASE_MARKERS_OBSERVED' if values else 'MISSING_PHASE_EVIDENCE')
  # Optional single canonical file only, never recurse or inspect saves.
  raw,_=command('container',['xcrun','simctl','get_app_container',udid,APP,'data']);file=safe_file(raw.decode().strip(),udid)
  report['canonicalGodotLogExists']=file.is_file()
  if file.is_file():
   with file.open('rb') as stream:data=stream.read(MAX_BYTES)
   rows=[typed_marker(x) for x in data.decode('utf-8','replace').splitlines()];added=0
   for value in rows:
    if value is not None and value not in report['phaseEvents'] and len(report['phaseEvents'])<MAX_RECORDS:report['phaseEvents'].append(value);added+=1
   report['canonicalFileCoverage']={'bytesRetained':len(data),'additionalTypedRecords':added,'readBoundBytes':MAX_BYTES}
  report['evidenceStatus']='TYPED_PHASE_MARKERS_OBSERVED' if report['phaseEvents'] else 'MISSING_PHASE_EVIDENCE'
  report['status']='CAPABILITY_PROBE_COMPLETED_DIAGNOSTIC_ONLY'
 except (ProbeStop,OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
  report['status']='CAPABILITY_UNAVAILABLE_OR_FAILED';report['failureCode']=str(error) if isinstance(error,ProbeStop) else type(error).__name__
 finally:
  if owner:
   try:
    confirm();image=output/'cold-diagnostic-raw.png';command('cold-frame',['xcrun','simctl','io',owner['udid'],'screenshot','--type=png',image],seconds=180)
    data=image.read_bytes();require(data[:8]==b'\x89PNG\r\n\x1a\n' and len(data)>33,'NATIVE_PNG_REQUIRED');report['frame']={'file':image.name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'width':int.from_bytes(data[16:20],'big'),'height':int.from_bytes(data[20:24],'big'),'diagnosticOnly':True,'resized':False}
   except (ProbeStop,OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):report['frameUnavailable']=True
  try:
   for child in list(children):
    confirmed=False;failure=None;signal_race=False
    try:
     if child.poll() is None:
      try:os.killpg(child.pid,signal.SIGTERM)
      except ProcessLookupError:signal_race=True
     try:child.wait(timeout=5)
     except subprocess.TimeoutExpired:
      try:os.killpg(child.pid,signal.SIGKILL)
      except ProcessLookupError:signal_race=True
      child.wait(timeout=5)
     confirmed=child.poll() is not None
    except (OSError,subprocess.TimeoutExpired) as error:
     failure=type(error).__name__
     try:confirmed=child.poll() is not None
     except OSError:confirmed=False
    report['cleanup'].append({'ownedChildClosed':confirmed,'signalExitRaceObserved':signal_race,'failureType':failure})
    if not confirmed:report['cleanupIncomplete']=True
  finally:
   try:
    if owner:
     try:
      confirm();command('terminate',['xcrun','simctl','terminate',owner['udid'],APP],allow_failure=True);command('shutdown',['xcrun','simctl','shutdown',owner['udid']],allow_failure=True);command('delete',['xcrun','simctl','delete',owner['udid']]);report['cleanup'].append({'ownSimulator':'deleted'})
     except (ProbeStop,OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):report['cleanup'].append({'ownSimulator':'identity-or-delete-unconfirmed'});report['cleanupIncomplete']=True
   finally:
    try:
     require(inside(scratch,root) and scratch.name.startswith('seven-log-sink-') and not scratch.is_symlink(),'OWNED_SCRATCH_ONLY');shutil.rmtree(scratch);report['cleanup'].append({'privateScratch':'removed'})
    except (ProbeStop,OSError):report['cleanup'].append({'privateScratch':'remove-unconfirmed'});report['cleanupIncomplete']=True
    if report.get('cleanupIncomplete'):report['status']='CAPABILITY_CLEANUP_UNCONFIRMED'
    try:publish()
    except OSError:report['publicReportWriteConfirmed']=False
 return report
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--metadata',required=True);parser.add_argument('--verifier',required=True);parser.add_argument('--output',required=True);a=parser.parse_args()
 try:result=run_probe(a.source,a.metadata,a.verifier,a.output);print(json.dumps({'status':result['status'],'nativeRuntimeReady':False}));sys.exit(0 if result['status']=='CAPABILITY_PROBE_COMPLETED_DIAGNOSTIC_ONLY' else 2)
 except ProbeStop as error:print(json.dumps({'status':'CAPABILITY_UNAVAILABLE_OR_FAILED','failureCode':str(error),'nativeRuntimeReady':False}));sys.exit(2)
