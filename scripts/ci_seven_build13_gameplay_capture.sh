#!/bin/bash
# Exact-source unsigned iOS Simulator gameplay capture; no Apple Store writes.
set +x
set -euo pipefail
umask 077

source_root="${1:?Verified source root required}"
project="${2:?Explicit project required}"
out="${3:?Gameplay output directory required}"
metadata="${4:?Pinned source metadata required}"
tools="$(cd "$(dirname "$0")" && pwd)"
verify="$tools/ci_verify_seven_build13.py"
probe="$tools/seven_build13_gameplay_probe"
[[ "$(uname -s)" == Darwin && -n "${RUNNER_TEMP:-}" && -f "$verify" && -d "$probe" ]] || {
  echo 'Pinned macOS gameplay tools required'; exit 2;
}
[[ -z "${GH_TOKEN:-}" && -z "${GITHUB_TOKEN:-}" ]] || {
  echo 'Gameplay capture refuses GitHub tokens'; exit 2;
}
[[ "$project" == seven-district-reckoning ]] || { echo 'Unknown Godot project'; exit 2; }
[[ "$(uname -m)" == x86_64 ]] || { echo 'Actual Intel macOS runner required'; exit 2; }
source_root="$(cd "$source_root" && pwd)"
mkdir -p "$out"
out="$(cd "$out" && pwd)"
scratch="$(mktemp -d "$RUNNER_TEMP/seven-build13-gameplay.XXXXXXXX")"
devices=()

cleanup() {
  status=$?
  trap - EXIT INT TERM
  set +e
  if [[ "$status" -ne 0 ]]; then
    python3 - "$out" "$scratch" <<'PY'
import hashlib,json,pathlib,re,shutil,struct,sys
from collections import deque
root=pathlib.Path(sys.argv[1]);scratch=pathlib.Path(sys.argv[2]);label=scratch/'last-phase'
text=label.read_text().strip() if label.exists() else 'unknown'
code='GAMEPLAY_'+re.sub('[^A-Z0-9]+','_',text.upper()).strip('_')+'_FAILED'
progress=deque(maxlen=8);critical=deque(maxlen=12);fallback=deque(maxlen=10)
logs=[scratch/(text+'.log')]
if text in ('iphone-probe','ipad-probe'):
 logs.insert(0,scratch/text/'xcodebuild-ui-test.log')
for log in logs:
 if not log.is_file():continue
 with log.open('rb') as stream:
  stream.seek(max(0,log.stat().st_size-8*1024*1024))
  lines=stream.read().decode('utf-8','replace').splitlines()
 for line in lines:
  line=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',line).strip()
  line=re.sub(r'/(?:Users|private|var|Volumes|home)/[^\s\"\'<>]+','<path>',line)
  line=re.sub(r'[\x00-\x1f\x7f]',' ',line)[:500]
  if not line:continue
  fallback.append(line)
  if 'Failed to send CA Event' in line:continue
  if 'SEVEN_' in line:progress.append(line)
  if re.search(r'error:|failed|failure|XCTAssert|No visible|Start tap|BUILD FAILED|TEST FAILED|UI test exited|Timed out waiting|Native screenshot geometry',line,re.I):
   critical.append(line)
diagnostics=list(progress)
diagnostics.extend(line for line in critical if line not in diagnostics)
if not diagnostics:diagnostics=list(fallback)
receipt=root/'gameplay-failure.json'
if not receipt.exists():
 partial=[];total=0;probe_exits=[]
 sources=[('activation','activation-simctl-raw.png'),
  ('activation-failure','activation-failure-simctl-raw.png'),
  ('title-wait-t120','title-wait-t120-simctl-raw.png'),
  ('title-wait-t240','title-wait-t240-simctl-raw.png'),
  ('title-wait-t360','title-wait-t360-simctl-raw.png'),
  ('title-wait-final','title-wait-final-simctl-raw.png'),
  ('title','title-simctl-raw.png'),('main001','main001-simctl-raw.png')]
 for kind in ('iphone','ipad'):
  probe=scratch/(kind+'-probe')
  exit_path=probe/'probe-exit.json'
  if exit_path.is_file() and not exit_path.is_symlink() and exit_path.stat().st_size<=4096:
   value=json.loads(exit_path.read_text())
   probe_exits.append({'kind':kind,'phase':str(value.get('phase',''))[:80],
                       'exitCode':value.get('exitCode')})
  for phase,source in sources:
   image=probe/source
   if not image.is_file() or image.is_symlink() or not 0<image.stat().st_size<=24*1024**2:
    continue
   with image.open('rb') as stream:head=stream.read(26)
   if (len(head)!=26 or head[:8]!=b'\x89PNG\r\n\x1a\n' or head[12:16]!=b'IHDR'
       or total+image.stat().st_size>150*1024**2):
    continue
   width,height=struct.unpack('>II',head[16:24])
   if not 0<width<=4096 or not 0<height<=4096:continue
   target=root/'partial'/(kind+'-'+phase+'.png')
   target.parent.mkdir(exist_ok=True)
   shutil.copyfile(image,target)
   total+=target.stat().st_size
   with target.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
   partial.append({'file':'partial/'+target.name,'bytes':target.stat().st_size,
                   'sha256':sha,'width':width,'height':height,
                   'listingCandidate':False,
                   'provenance':'raw simctl screenshot from bounded XCUITest probe before failure'})
 receipt.write_text(json.dumps({'projectId':'seven-district-reckoning','phase':'gameplay-capture',
  'failureCode':code[:80],'rawLogsPublished':False,'appleSecretsUsed':False,
  'storeUploadPerformed':False,'diagnostics':diagnostics,
  'probeExitReceipts':probe_exits,'partialScreenshots':partial},indent=2)+'\n',encoding='utf-8')
PY
  fi
  for device in "${devices[@]}"; do
    if [[ "$device" =~ ^[A-Fa-f0-9-]{36}$ ]]; then
      xcrun simctl shutdown "$device" >/dev/null 2>&1
      xcrun simctl delete "$device" >/dev/null 2>&1
    fi
  done
  python3 - "$scratch" "$RUNNER_TEMP" <<'PY'
import pathlib,shutil,sys
target=pathlib.Path(sys.argv[1]).resolve();parent=pathlib.Path(sys.argv[2]).resolve()
if target!=parent and target.is_relative_to(parent) and target.name.startswith('seven-build13-gameplay.'):
 shutil.rmtree(target,ignore_errors=True)
PY
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

safe_cmd() {
  label="$1"; limit="$2"; shift 2
  printf '%s\n' "$label" > "$scratch/last-phase"
  python3 - "$scratch/$label.log" "$limit" "$@" <<'PY'
import os,pathlib,signal,subprocess,sys
log=pathlib.Path(sys.argv[1]);limit=int(sys.argv[2]);args=sys.argv[3:]
with log.open('wb') as stream:
 try:
  process=subprocess.Popen(args,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
  try:code=process.wait(timeout=limit)
  except subprocess.TimeoutExpired:
   os.killpg(process.pid,signal.SIGTERM)
   try:process.wait(timeout=10)
   except subprocess.TimeoutExpired:
    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
   raise SystemExit('Bounded gameplay command timed out: '+log.stem)
 except OSError:raise SystemExit('Bounded gameplay command could not start: '+log.stem)
if code:raise SystemExit('Bounded gameplay command failed: '+log.stem)
PY
}

printf 'verify-source\n' > "$scratch/last-phase"
python3 "$verify" source --root "$source_root" --metadata "$metadata" \
  --project "$project" --output "$out/source-verification.json" >/dev/null
xcodebuild -version > "$scratch/xcode.txt"
python3 - "$scratch/xcode.txt" <<'PY'
import pathlib,re,sys
if not re.fullmatch(r'Xcode 26\.3\s+Build version 17C529\s*',pathlib.Path(sys.argv[1]).read_text().strip()):
 raise SystemExit('Exact Xcode 26.3/17C529 required')
PY

printf 'verify-simulator-architecture\n' > "$scratch/last-phase"
python3 - "$source_root" "$out" <<'PY'
import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);rows=[]
for slice_name,expected in [('ios-arm64','arm64'),('ios-arm64_x86_64-simulator','x86_64')]:
 library=root/'SevenDistrict.xcframework'/slice_name/'libgodot.a'
 result=subprocess.run(['xcrun','lipo','-archs',str(library)],capture_output=True,text=True,timeout=60)
 if result.returncode or result.stdout.split()!=[expected]:
  raise SystemExit('Pinned Godot library architecture differs')
 rows.append({'slice':slice_name,'architecture':expected,
              'sha256':hashlib.sha256(library.read_bytes()).hexdigest()})
(out/'simulator-architecture.json').write_text(json.dumps({'projectId':'seven-district-reckoning',
 'runnerArchitecture':'x86_64','simulatorArchitecture':'x86_64','deviceArchitecture':'arm64',
 'libraries':rows,'sourceFilesChanged':False},indent=2)+'\n')
PY

safe_cmd sim-build 2400 xcodebuild -project "$source_root/SevenDistrict.xcodeproj" \
  -scheme SevenDistrict -configuration Debug -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath "$scratch/derived-sim" \
  CODE_SIGNING_ALLOWED=NO ONLY_ACTIVE_ARCH=NO ARCHS=x86_64 EXCLUDED_ARCHS=arm64 build
app="$scratch/derived-sim/Build/Products/Debug-iphonesimulator/SevenDistrict.app"
printf 'verify-simulator-app\n' > "$scratch/last-phase"
python3 "$verify" app --root "$source_root" --project "$project" --app "$app" \
  --output "$out/simulator-verification.json" >/dev/null

printf 'select-simulator-models\n' > "$scratch/last-phase"
xcrun simctl list --json > "$scratch/inventory.json"
python3 - "$scratch" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]);inventory=json.loads((p/'inventory.json').read_text())
runtimes=[r for r in inventory['runtimes'] if r.get('isAvailable') is True
 and not r.get('availabilityError') and r['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-')
 and r['version'].split('.')[0]=='26']
runtimes.sort(key=lambda r:tuple(map(int,r['version'].split('.'))),reverse=True)
phone=[d for d in inventory['devicetypes'] if d['name']=='iPhone 17 Pro']
tablet=[d for d in inventory['devicetypes'] if d['name'].startswith('iPad Pro 13-inch (M4)')]
tablet.sort(key=lambda d:('16GB' not in d['name'],d['name']))
if not runtimes or len(phone)!=1 or not tablet:raise SystemExit('Required real Simulator models/runtime unavailable')
runtime=runtimes[0];encoded=int(runtime['version'].split('.')[0])*65536+int(runtime['version'].split('.')[1])*256
for model in (phone[0],tablet[0]):
 if not model.get('minRuntimeVersion',0)<=encoded<=model.get('maxRuntimeVersion',0xffffffff):
  raise SystemExit('Required model incompatible with available runtime')
for field,value in [('runtime',runtime['identifier']),('phone-type',phone[0]['identifier']),
                    ('tablet-type',tablet[0]['identifier'])]:(p/field).write_text(value)
(p/'models.json').write_text(json.dumps({'runtime':runtime['version'],
 'iphone':phone[0]['name'],'ipad':tablet[0]['name']}))
(p/'previous-devices.json').write_text(json.dumps([d['udid'].lower()
 for group in inventory.get('devices',{}).values() for d in group]))
PY
runtime="$(cat "$scratch/runtime")"
mkdir -p "$out/raw" "$out/candidates"
for kind in iphone ipad; do
  if [[ "$kind" == iphone ]]; then model="$(cat "$scratch/phone-type")"; else model="$(cat "$scratch/tablet-type")"; fi
  printf '%s\n' "$kind-create" > "$scratch/last-phase"
  device="$(xcrun simctl create "Mars-Seven-build13-${GITHUB_RUN_ID:-local}-$kind" "$model" "$runtime")"
  python3 - "$device" "$scratch/previous-devices.json" <<'PY'
import json,re,sys
uuid=sys.argv[1]
if (not re.fullmatch(r'[A-Fa-f0-9]{8}(?:-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}',uuid)
    or uuid.lower() in json.load(open(sys.argv[2]))):
 raise SystemExit('Simulator ID was not newly created')
PY
  devices+=("$device")
  printf '%s\n' "$device" > "$scratch/$kind-udid"
  safe_cmd "$kind-boot" 180 xcrun simctl boot "$device"
  safe_cmd "$kind-bootstatus" 600 xcrun simctl bootstatus "$device" -b
  safe_cmd "$kind-statusbar" 60 xcrun simctl status_bar "$device" override \
    --time 9:41 --batteryState charged --batteryLevel 100
  safe_cmd "$kind-install" 360 xcrun simctl install "$device" "$app"
  safe_cmd "$kind-probe" 1500 bash "$probe/run_probe.sh" "$device" "$scratch/$kind-probe"
  python3 - "$scratch/$kind-probe" "$out/raw" "$kind" <<'PY'
import pathlib,shutil,sys
probe=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);kind=sys.argv[3]
for source,target in [('activation-simctl-raw.png',f'{kind}-activation.png'),
                      ('title-simctl-raw.png',f'{kind}-title.png'),
                      ('main001-simctl-raw.png',f'{kind}-main001.png')]:
 p=probe/source
 if not p.is_file() or p.is_symlink():raise SystemExit('Real simctl capture missing')
 shutil.copyfile(p,out/target)
for source,target in [('activation-simctl-evidence.json',f'{kind}-activation-evidence.json'),
                      ('title-simctl-evidence.json',f'{kind}-title-evidence.json'),
                      ('main001-simctl-evidence.json',f'{kind}-main001-evidence.json')]:
 p=probe/source
 if not p.is_file() or p.is_symlink():raise SystemExit('Real simctl receipt missing')
 shutil.copyfile(p,out.parent/target)
PY
  safe_cmd "$kind-shutdown" 60 xcrun simctl shutdown "$device"
done

cat > "$scratch/rgb.swift" <<'SWIFT'
import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
func stop() -> Never { fputs("Native RGB conversion failed\n",stderr);exit(1) }
let input=URL(fileURLWithPath:CommandLine.arguments[1]);let output=URL(fileURLWithPath:CommandLine.arguments[2])
let width=Int(CommandLine.arguments[3])!;let height=Int(CommandLine.arguments[4])!
guard let source=CGImageSourceCreateWithURL(input as CFURL,nil),let image=CGImageSourceCreateImageAtIndex(source,0,nil),
      image.width==width && image.height==height else {stop()}
guard let canvas=CGContext(data:nil,width:width,height:height,bitsPerComponent:8,
      bytesPerRow:width*4,space:CGColorSpaceCreateDeviceRGB(),
      bitmapInfo:CGImageAlphaInfo.noneSkipLast.rawValue) else {stop()}
canvas.interpolationQuality = .none
canvas.draw(image,in:CGRect(x:0,y:0,width:CGFloat(width),height:CGFloat(height)))
guard let rgb=canvas.makeImage(),let destination=CGImageDestinationCreateWithURL(output as CFURL,
      UTType.png.identifier as CFString,1,nil) else {stop()}
CGImageDestinationAddImage(destination,rgb,nil);guard CGImageDestinationFinalize(destination) else {stop()}
SWIFT
for kind in iphone ipad; do
  if [[ "$kind" == iphone ]]; then width=2622; height=1206; else width=2752; height=2064; fi
  safe_cmd "$kind-native-rgb" 180 xcrun swift "$scratch/rgb.swift" \
    "$out/raw/$kind-main001.png" "$out/candidates/$kind-main001.png" "$width" "$height"
done

printf 'verify-gameplay-receipts\n' > "$scratch/last-phase"
python3 - "$out" "$scratch/models.json" "$scratch/iphone-udid" "$scratch/ipad-udid" <<'PY'
import hashlib,json,pathlib,struct,sys
root=pathlib.Path(sys.argv[1]);models=json.loads(pathlib.Path(sys.argv[2]).read_text())
ids={'iphone':pathlib.Path(sys.argv[3]).read_text().strip(),
     'ipad':pathlib.Path(sys.argv[4]).read_text().strip()}
if models.get('iphone')!='iPhone 17 Pro' or not models.get('ipad','').startswith('iPad Pro 13-inch (M4)'):
 raise SystemExit('Actual required models differ')
captures=[]
for kind in ('iphone','ipad'):
 expected=(2622,1206) if kind=='iphone' else (2752,2064)
 activation=json.loads((root/f'{kind}-activation-evidence.json').read_text())
 title=json.loads((root/f'{kind}-title-evidence.json').read_text())
 play=json.loads((root/f'{kind}-main001-evidence.json').read_text())
 files={'activationRaw':root/'raw'/f'{kind}-activation.png',
        'titleRaw':root/'raw'/f'{kind}-title.png',
        'gameplayRaw':root/'raw'/f'{kind}-main001.png',
        'listingCandidate':root/'candidates'/f'{kind}-main001.png'}
 hashes={}
 for key,path in files.items():
  raw=path.read_bytes()
  if (raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR'
      or struct.unpack('>II',raw[16:24])!=expected or (key=='listingCandidate' and raw[25]!=2)):
   raise SystemExit('Native orientation, PNG or opaque RGB candidate differs')
  hashes[key]=hashlib.sha256(raw).hexdigest()
 orientation='landscapeLeft' if kind=='iphone' else 'landscapeRight'
 if (activation.get('sha256')!=hashes['activationRaw']
     or title.get('sha256')!=hashes['titleRaw'] or play.get('sha256')!=hashes['gameplayRaw']
     or (activation.get('width'),activation.get('height'))!=expected
     or (title.get('width'),title.get('height'))!=expected
     or (play.get('width'),play.get('height'))!=expected
     or 'phase=activated' not in activation.get('uiTestGate','')
     or 'orientation='+orientation not in activation.get('uiTestGate','')
     or activation.get('nativeGeometryAccepted') is not True
     or title.get('nativeGeometryAccepted') is not True
     or play.get('nativeGeometryAccepted') is not True
     or 'bundle=tw.mars.sevendistrictreckoning' not in title.get('uiTestGate','')
     or 'orientation='+orientation not in title.get('uiTestGate','')
     or 'orientation='+orientation not in play.get('uiTestGate','')
     or 'startVisible=true' not in title.get('uiTestGate','')
     or 'startOCRBox=' not in title.get('uiTestGate','')
     or 'startXCUIScreenPoint=' not in title.get('uiTestGate','')
     or 'startCoordinateErrorPoints=' not in title.get('uiTestGate','')
     or 'mission=MAIN-001' not in play.get('uiTestGate','')
     or 'startTapNormalized=' not in play.get('uiTestGate','')):
  raise SystemExit('XCUITest title/tap/MAIN-001 handshake differs')
 captures.append({'kind':kind,'model':models[kind],'deviceId':ids[kind],
  'orientation':orientation,
  'activationRaw':f'raw/{kind}-activation.png','activationRawSha256':hashes['activationRaw'],
  'titleRaw':f'raw/{kind}-title.png','titleRawSha256':hashes['titleRaw'],
  'gameplayRaw':f'raw/{kind}-main001.png','gameplayRawSha256':hashes['gameplayRaw'],
  'listingCandidate':f'candidates/{kind}-main001.png',
  'listingCandidateSha256':hashes['listingCandidate'],
  'startTappedByXCUITest':True,'main001VerifiedByXCUITest':True,
  'nativeResolution':True,'cropApplied':False,'syntheticContentAdded':False})
receipt={'projectId':'seven-district-reckoning','version':'1.0.0','build':13,
 'sourcePckSha256':'adb2466826ce250b8b357b706b3520c9e69792a2fceb06da5bbd3f724a9f9439',
 'runtime':models['runtime'],'actualSimulator':True,'captures':captures,
 'visualReviewPending':True,'listingUploadReady':False,'appleSecretsUsed':False,
 'storeUploadPerformed':False}
(root/'gameplay-capture.json').write_text(json.dumps(receipt,indent=2)+'\n')
PY
echo 'Real MAIN-001 Simulator frames captured; visual review still required.'
