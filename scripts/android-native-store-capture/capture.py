"""Actual signed APK + native framebuffer + visible accessibility UI touches.

Never runs on the owner's computer. No browser automation, state injection,
coordinate guessing, frame resizing, rendering-rate change or signer keys.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageChops

ACTIONS={
 'night-train-watch-protocol':[r'R01.*灰霧',r'^(開始旅程|繼續|開始這段)'],
 'tower-defense-skill':[r'^快速開始',r'^建議位',r'^確認建(塔|造)'],
 'web-card-game-skill':[r'^略過(?:教學)?$',r'^結束回合'],
 'ashes-convoy':[r'^(出勤|開始出勤)',r'^(開始護送|出發)'],
 'island-flight-school':[r'^(開始飛行|跟我飛|開始課程|開始練習|起飛)',r'^繼續'],
 'taiwan-train-school':[r'準備出發',r'開始前進'],
 'pixel-idle-farm-skill':[r'^(把農場接回來|開始種田)',r'^訂單$'],
 'village-siege':[r'^(開始遊戲|開始戰役|開始守城|開始|遊玩)',r'^繼續'],
 'storm-apocalypse':[r'^(確認屠夫老闆娘|開始遊戲|開始戰役|出擊|開始)',r'^繼續'],
 'taiwan-train-math':[r'^遊戲室$',r'^火車圖鑑$'],
 'taiwan-island-drive':[r'^(開始駕駛|開始遊戲|出發|開始)',r'^繼續'],
 'crackveil-vanguard':[r'^(PLAY|START|開始|出擊)'],
 'seven-district-reckoning':[r'^(PLAY|START|開始|出發)'],
}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def run(argv,timeout=45):
 r=subprocess.run(argv,capture_output=True,timeout=timeout)
 if r.returncode:raise RuntimeError('Native command failed: '+Path(argv[0]).name+' exit'+str(r.returncode))
 return r.stdout
def observed_target(nodes,patterns,width,height,package):
 choices=[]
 for node in nodes:
  if node.get('package')!=package or node.get('clickable')!='true' or node.get('enabled')=='false':continue
  label=(node.get('text','')+' '+node.get('content-desc','')).strip()
  if not any(re.search(pattern,label) for pattern in patterns):continue
  m=re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',node.get('bounds',''))
  if not m:continue
  l,t,r,b=map(int,m.groups())
  if not 0<=l<r<=width or not 0<=t<b<=height:continue
  choices.append(((r-l)*(b-t),label,[l,t,r,b],[(l+r)//2,(t+b)//2]))
 return min(choices,key=lambda x:x[0]) if choices else None
def observed_loading(nodes,package):
 text='\n'.join(n.get('text','')+' '+n.get('content-desc','') for n in nodes if n.get('package')==package)
 return bool(re.search(r'正在準備駕駛艙|載入 Blender 模型|準備戰場|正在下載角色與建築素材',text))

def main():
 p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--family',choices=['phone','tablet'],required=True);p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--avd',required=True);a=p.parse_args()
 if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!='mars-tw/taiwan-train-math':raise RuntimeError('This driver runs only in the owned GitHub CI VM')
 source=Path(a.input).resolve();out=Path(a.output).resolve();temp=Path(os.environ['RUNNER_TEMP']).resolve();workspace=Path(os.environ['GITHUB_WORKSPACE']).resolve()
 if not source.is_relative_to(temp) or not out.is_relative_to(workspace):raise RuntimeError('Input/output scope mismatch')
 out.mkdir(parents=True,exist_ok=True);manifest=json.loads((source/'android-capture-manifest.json').read_text())
 items=[i for i in manifest['projects'] if i['projectId']==a.project]
 if len(items)!=1:raise RuntimeError('One exact project required')
 item=items[0];apk=source/item['apkFile'];package=item['packageName']
 sdk=Path(os.environ['ANDROID_HOME']);adb=str(sdk/'platform-tools/adb');build=sdk/'build-tools/36.0.0';serial='emulator-5554'
 def ad(*args,timeout=45):return run([adb,'-s',serial,*args],timeout)
 if ad('emu','avd','name').decode().splitlines()[0].strip()!=a.avd:raise RuntimeError('Serial belongs to another AVD')
 if sha(apk.read_bytes())!=item['apkSha256']:raise RuntimeError('APK mutated after relay')
 if ad('shell','getprop','ro.build.version.sdk').decode().strip()!='36':raise RuntimeError('API36 device required')
 report={'status':'PREPARING','projectId':a.project,'packageName':package,'version':item['version'],'build':item['build'],'family':a.family,'apiLevel':36,'avd':a.avd,'deviceOrigin':'fresh GitHub-hosted Android Emulator','apkSha256':item['apkSha256'],'apkBytes':item['apkBytes'],'expectedCertificateSha256':item['certificateSha256'],'sourceReceiptSha256':item['sourceReceiptSha256'],'sourceManifestSha256':item.get('sourceManifestSha256'),'sourceTag':item.get('sourceTag'),'sourceRunId':item.get('sourceRunId'),'githubRunId':os.environ['GITHUB_RUN_ID'],'workflowCommit':os.environ['GITHUB_SHA'],'physicalDeviceTested':False,'signerSecretsUsed':False,'uiStateInjected':False,'screenResizedOrCropped':False,'screenshots':[],'actions':[],'warnings':[],'visualReviewRequired':True,'startedAtUtc':now()}
 def save(): (out/'receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 def foreground():
  data=ad('shell','dumpsys','activity','activities').decode('utf-8','replace')
  lines=[line.strip() for line in data.splitlines() if 'ResumedActivity' in line or 'topResumedActivity' in line]
  if not any(package+'/' in line for line in lines):raise RuntimeError('Own app is not foreground')
  return lines
 def capture(label):
  fg=foreground();raw=ad('exec-out','screencap','-p');rawpath=out/(label+'-raw-native.png');rawpath.write_bytes(raw)
  with Image.open(rawpath) as im:
   im.load()
   if min(im.size)<320 or max(im.size)>3840 or max(im.size)>2*min(im.size):raise RuntimeError('Actual framebuffer dimensions not Google eligible')
   expected=(1080,1920) if a.family=='phone' else (1200,1920)
   if im.size not in {expected,expected[::-1]}:raise RuntimeError('Unexpected native framebuffer size')
   if im.mode=='RGBA' and im.getchannel('A').getextrema()!=(255,255):raise RuntimeError('Nonopaque native framebuffer cannot be losslessly RGB encoded')
   rgb=im.convert('RGB');path=out/(label+'.png');rgb.save(path,format='PNG')
   if Image.open(path).convert('RGB').tobytes()!=rgb.tobytes():raise RuntimeError('RGB encoding changed framebuffer colors')
   entry={'file':path.name,'rawFile':rawpath.name,'width':im.width,'height':im.height,'mode':'RGB','bytes':path.stat().st_size,'sha256':sha(path.read_bytes()),'rawSha256':sha(raw),'pixelSha256':sha(rgb.tobytes()),'nativeForeground':fg,'capturedAtUtc':now(),'rawMode':im.mode,'rgbEncodingLossless':True}
   report['screenshots'].append(entry);save();return entry
 def hierarchy(label):
  remote='/sdcard/native-capture-'+a.project+'.xml'
  ad('shell','uiautomator','dump','--compressed',remote,timeout=30)
  raw=ad('exec-out','cat',remote);(out/(label+'.xml')).write_bytes(raw)
  root=ET.fromstring(raw);nodes=[n.attrib for n in root.iter('node')]
  return nodes
 try:
  signed=run([str(build/'apksigner'),'verify','--verbose','--print-certs',str(apk)]).decode('utf-8','replace')
  certs=re.findall(r'certificate SHA-256 digest: ([0-9a-f]{64})',signed)
  if certs!=[item['certificateSha256']]:raise RuntimeError('Signed APK certificate mismatch')
  badging=run([str(build/'aapt'),'dump','badging',str(apk)]).decode('utf-8','replace')
  m=re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'",badging)
  if not m or (m[1],int(m[2]),m[3])!=(package,item['build'],item['version']) or 'application-debuggable' in badging:raise RuntimeError('APK identity/version/release mismatch')
  report.update(signatureVerified=True,certificateSha256=certs[0],debuggable=False,deviceAbiList=ad('shell','getprop','ro.product.cpu.abilist').decode().strip(),nativeBridge=ad('shell','getprop','ro.dalvik.vm.native.bridge').decode().strip())
  if item.get('nativeAbis') and not any(abi in report['deviceAbiList'].split(',') for abi in item['nativeAbis']):
   report['status']='HOLD_NO_COMPATIBLE_NATIVE_ABI';report['error']='Device ABI/native bridge does not support this unchanged release APK';save();return 2
  ad('shell','input','keyevent','82');install=ad('install','--no-streaming',str(apk),timeout=120).decode()
  if 'Success' not in install:raise RuntimeError('APK install did not report Success')
  report['installVerified']=True
  installed=ad('shell','dumpsys','package',package).decode('utf-8','replace')
  if 'versionName='+item['version'] not in installed or not re.search(r'\bversionCode='+str(item['build'])+r'\b',installed):raise RuntimeError('Installed package does not match signed input')
  component=ad('shell','cmd','package','resolve-activity','--brief',package).decode().strip().splitlines()[-1]
  if not component.startswith(package+'/') or not re.fullmatch(r'[A-Za-z0-9._/$]+',component):raise RuntimeError('Unexpected resolved activity')
  ad('logcat','-c');ad('shell','am','start','-W','-n',component)
  report['resolvedActivity']=component;save()
  deadline=time.monotonic()+150;nodes=[];candidate=None
  while time.monotonic()<deadline:
   time.sleep(4)
   try:
    screen=capture('01-launched') if not report['screenshots'] else None
    nodes=hierarchy('01-launched');w,h=report['screenshots'][0]['width'],report['screenshots'][0]['height']
    candidate=observed_target(nodes,[ACTIONS[a.project][0]],w,h,package)
    if observed_loading(nodes,package):candidate=None
    if candidate:break
   except Exception as error:report['warnings'].append('Readiness: '+str(error));save()
  # Refresh first frame once actual control exists; initial startup observation
  # is retained separately rather than advertised as a fully loaded menu.
  if candidate:
   capture('02-ready-menu')
  else:
   report['status']='HOLD_NO_OBSERVED_ACCESSIBLE_START_CONTROL';report['error']='First native image retained; no guessed touch or state injection';save();return 2
  for index,pattern in enumerate(ACTIONS[a.project]):
   try:
    before=capture('pre-action-'+str(index+1));nodes=hierarchy('pre-action-'+str(index+1))
    target=observed_target(nodes,[pattern],before['width'],before['height'],package)
    if not target:
     if index==0:raise RuntimeError('Observed first control disappeared')
     report['warnings'].append('Optional next visible control not present: '+pattern);break
    area,label,bounds,point=target
    report['actions'].append({'label':label,'selector':pattern,'bounds':bounds,'nativePixelPoint':point,'basis':'current actual UI hierarchy + native framebuffer bounds','beforeScreenshot':before['file'],'startedAtUtc':now()});save()
    ad('shell','input','tap',str(point[0]),str(point[1]));tapped_at=time.monotonic();time.sleep(8)
    if a.project=='village-siege' and index==0:
     report['villageFrozenReleaseLoadingProbes']=[]
     for seconds in [30,60,90]:
      time.sleep(max(0,tapped_at+seconds-time.monotonic()))
      entry={'secondsAfterActualStartTouch':seconds}
      try:
       frame=capture('village-probe-'+str(seconds)+'s');probe_nodes=hierarchy('village-probe-'+str(seconds)+'s')
       entry.update(screenshot=frame['file'],loadingVisible=observed_loading(probe_nodes,package),visibleLabels=[n.get('text','')+' '+n.get('content-desc','') for n in probe_nodes if n.get('package')==package and (n.get('text') or n.get('content-desc'))][:120])
       pid=ad('shell','pidof',package).decode().strip()
       if pid.isdigit():(out/('village-probe-'+str(seconds)+'s-own-app.log')).write_bytes(ad('logcat','-d','--pid='+pid,'-v','brief',timeout=15))
      except Exception as error:entry['error']=str(error)
      report['villageFrozenReleaseLoadingProbes'].append(entry);save()
    load_deadline=time.monotonic()+120
    while True:
     loaded_nodes=hierarchy('loading-observation-'+str(index+1))
     if not observed_loading(loaded_nodes,package):break
     if time.monotonic()>load_deadline:raise RuntimeError('Actual loading UI did not finish; do not accept loading as gameplay')
     time.sleep(5)
    after=capture('03-after-action-'+str(index+1))
    after_nodes=hierarchy('03-after-action-'+str(index+1));report['actions'][-1]['afterVisibleLabels']=[(n.get('text','')+' '+n.get('content-desc','')).strip() for n in after_nodes if n.get('package')==package and (n.get('text') or n.get('content-desc'))][:150]
    with Image.open(out/before['file']) as ia,Image.open(out/after['file']) as ib:
     if ia.size==ib.size:
      hist=ImageChops.difference(ia,ib).convert('L').histogram();changed=100*(ia.width*ia.height-hist[0])/(ia.width*ia.height)
     else:changed=100
    report['actions'][-1].update(afterScreenshot=after['file'],changedLuminancePixelPercent=changed,foregroundVerified=True)
    save()
   except Exception as error:report['warnings'].append('Touch/navigation phase: '+str(error));break
  changed=[x for x in report['actions'] if x.get('changedLuminancePixelPercent',0)>3 and x.get('afterVisibleLabels')]
  report['status']='CAPTURED_NATIVE_INTERACTION_PENDING_VISUAL_QA' if changed else 'HOLD_SCENE_CHANGE_NOT_PROVEN'
  report['uiControlsExercised']=len([x for x in report['actions'] if x.get('foregroundVerified')]);report['nativeGameplayLoopCompleted']=False
  return 0 if changed else 2
 except Exception as error:
  report['status']='FAILED_NATIVE_CAPTURE';report['error']=str(error);return 2
 finally:
  try:
   pid=ad('shell','pidof',package).decode().strip()
   if pid.isdigit():
    raw=ad('logcat','-d','--pid='+pid,'-v','brief',timeout=15);(out/'own-app-logcat.log').write_bytes(raw)
    report['ownAppCrashIndicators']=bool(re.search(rb'FATAL EXCEPTION|Fatal signal|Unhandled|Uncaught (?:TypeError|ReferenceError|SyntaxError)',raw))
  except Exception as error:report['warnings'].append('Own app log: '+str(error))
  report['finishedAtUtc']=now();save();print(json.dumps({'projectId':a.project,'family':a.family,'status':report['status'],'screenshots':len(report['screenshots']),'actions':len(report['actions'])}))

if __name__=='__main__':raise SystemExit(main())
