#!/bin/bash
# Unsigned fresh simulator probe only; no source changes, signing or store APIs.
set -euo pipefail
app="${1:?extracted frozen app required}"
out="${2:?public probe output required}"
tools="${CI_TOOLS:?approved verifier folder required}"
[[ "$(uname -s)" == Darwin && -n "${RUNNER_TEMP:-}" ]] || exit 2
app="$(cd "$app" && pwd)";mkdir -p "$out";out="$(cd "$out" && pwd)"
scratch="$(mktemp -d "$RUNNER_TEMP/storm-ipad-probe.XXXXXX")"
device=""
cleanup() {
  set +e
  if [[ "$device" =~ ^[A-Fa-f0-9-]{36}$ ]]; then xcrun simctl shutdown "$device" >/dev/null 2>&1;xcrun simctl delete "$device" >/dev/null 2>&1;fi
  python3 - "$scratch" "$RUNNER_TEMP" <<'PY'
import pathlib,shutil,sys
p=pathlib.Path(sys.argv[1]).resolve();r=pathlib.Path(sys.argv[2]).resolve()
if p!=r and p.is_relative_to(r) and p.name.startswith('storm-ipad-probe.'):shutil.rmtree(p,ignore_errors=True)
PY
}
trap cleanup EXIT
safe_cmd() {
  local label="$1";shift
  python3 - "$scratch/$label.log" "$@" <<'PY'
import pathlib,subprocess,sys
try:
 with pathlib.Path(sys.argv[1]).open('wb') as f:r=subprocess.run(sys.argv[2:],stdout=f,stderr=subprocess.STDOUT,timeout=1800)
except (OSError,subprocess.TimeoutExpired):raise SystemExit('Unsigned probe command timed out; public label='+pathlib.Path(sys.argv[1]).stem) from None
if r.returncode:raise SystemExit('Unsigned probe command failed; public label='+pathlib.Path(sys.argv[1]).stem)
PY
}
python3 "$tools/ci_verify_ios.py" source --root "$app" --project storm-apocalypse --output "$out/source-verification.json"
xcrun simctl list runtimes -j > "$scratch/runtimes.json"
xcrun simctl list devicetypes -j > "$scratch/types.json"
python3 - "$scratch" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]);r=json.loads((p/'runtimes.json').read_text())['runtimes'];d=json.loads((p/'types.json').read_text())['devicetypes']
r=[v for v in r if v.get('isAvailable') and v['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-') and v['version'].split('.')[0]=='26'];r.sort(key=lambda v:tuple(map(int,v['version'].split('.'))),reverse=True)
d=[v for v in d if v['name'].startswith('iPad Pro 13-inch (M4)')];d.sort(key=lambda v:('16GB' not in v['name'],v['name']));d=d[:1]
if not r or len(d)!=1:raise SystemExit('Pinned runtime/iPad M4 unavailable')
(p/'runtime').write_text(r[0]['identifier']);(p/'device-type').write_text(d[0]['identifier'])
PY
device="$(xcrun simctl create "Mars-storm-ipad-probe-${GITHUB_RUN_ID:-local}" "$(cat "$scratch/device-type")" "$(cat "$scratch/runtime")")"
cd "$app"
safe_cmd unsigned-sim-build xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Debug -sdk iphonesimulator -destination "platform=iOS Simulator,id=$device" -derivedDataPath "$scratch/derived" CODE_SIGNING_ALLOWED=NO ONLY_ACTIVE_ARCH=YES build
binary="$scratch/derived/Build/Products/Debug-iphonesimulator/App.app"
python3 "$tools/ci_verify_ios.py" app --root "$app" --project storm-apocalypse --app "$binary" --output "$out/simulator-verification.json"
safe_cmd boot xcrun simctl boot "$device"
safe_cmd bootstatus xcrun simctl bootstatus "$device" -b
safe_cmd statusbar xcrun simctl status_bar "$device" override --time 9:41 --dataNetwork wifi --wifiMode active --wifiBars 3 --batteryState charged --batteryLevel 100
safe_cmd install xcrun simctl install "$device" "$binary"
mkdir -p "$out/screenshots"
for moment in cold warm; do
  if [[ "$moment" == warm ]]; then safe_cmd terminate xcrun simctl terminate "$device" tw.mars.stormapocalypse;fi
  safe_cmd "$moment-launch" xcrun simctl launch "$device" tw.mars.stormapocalypse
  launch_epoch="$(date +%s)"
  pid="$(python3 - "$scratch/$moment-launch.log" <<'PY'
import pathlib,re,sys
s=pathlib.Path(sys.argv[1]).read_text();m=re.search(r'tw\.mars\.stormapocalypse:\s*(\d+)',s)
if not m:raise SystemExit('Launch did not return own-App PID')
print(m[1])
PY
)"
  for seconds in 30 60 90; do
    sleep 30
    safe_cmd "$moment-$seconds-shot" xcrun simctl io "$device" screenshot --type=png "$scratch/$moment-$seconds.png"
    PROBE_OUTPUT="$out" PROBE_DEVICE="$device" PROBE_PID="$pid" PROBE_MOMENT="$moment" PROBE_SECONDS="$seconds" PROBE_LAUNCH_EPOCH="$launch_epoch" python3 - <<'PY'
import json,os,pathlib,subprocess,time
p=pathlib.Path(os.environ['PROBE_OUTPUT']);device=os.environ['PROBE_DEVICE'];pid=os.environ['PROBE_PID'];moment=os.environ['PROBE_MOMENT'];seconds=int(os.environ['PROBE_SECONDS'])
r=subprocess.run(['xcrun','simctl','spawn',device,'launchctl','procinfo',pid],capture_output=True,timeout=30)
with (p/'process-observations.jsonl').open('a') as f:f.write(json.dumps({'moment':moment,'minimumWaitSeconds':seconds,'actualElapsedSeconds':round(time.time()-int(os.environ['PROBE_LAUNCH_EPOCH']),1),'ownAppPid':int(pid),'processQueryExit':r.returncode,'rawOutputWithheld':True})+'\n')
PY
  done
done
PROBE_DEVICE="$device" PROBE_OUTPUT="$out" python3 - <<'PY'
import json,os,pathlib,subprocess
device=os.environ['PROBE_DEVICE'];p=pathlib.Path(os.environ['PROBE_OUTPUT'])
predicate='process == "App" OR process == "com.apple.WebKit.WebContent"'
r=subprocess.run(['xcrun','simctl','spawn',device,'log','show','--last','8m','--style','json','--predicate',predicate],capture_output=True,timeout=60)
categories={k:0 for k in ['webkit','navigation','javascript','terminated','crash','memory','other']};count=0
try:entries=json.loads(r.stdout) if r.returncode==0 else []
except (ValueError,TypeError):entries=[]
for entry in entries:
 if str(entry.get('messageType','')).lower() not in ('error','fault'):continue
 text=str(entry.get('eventMessage','')).lower();category=next((k for k in categories if k!='other' and k in text),'other');categories[category]+=1;count+=1
(p/'runtime-error-summary.json').write_text(json.dumps({'ownAppAndWebContentOnly':True,'errorAndFaultOnly':True,'logQueryExit':r.returncode,'events':count,'fixedCategoryCounts':categories,'rawMessagesWithheld':True,'signingSecretsUsed':False},indent=2)+'\n')
PY
SCREENSHOT_INPUT="$scratch" SCREENSHOT_OUTPUT="$out/screenshots" node --input-type=module <<'JS'
import sharp from 'sharp';import path from 'node:path';
for(const moment of ['cold','warm'])for(const seconds of [30,60,90]){
 const name=`${moment}-${seconds}.png`,source=path.join(process.env.SCREENSHOT_INPUT,name),meta=await sharp(source).metadata();
 if(meta.width!==2064||meta.height!==2752)throw Error('Unexpected native iPad M4 resolution');
 await sharp(source).removeAlpha().png({palette:false}).toFile(path.join(process.env.SCREENSHOT_OUTPUT,name));
}
JS
python3 - "$out" <<'PY'
import hashlib,json,pathlib,struct,sys
p=pathlib.Path(sys.argv[1]);records=[]
for f in sorted((p/'screenshots').glob('*.png')):
 data=f.read_bytes();w,h=struct.unpack('>II',data[16:24]);records.append({'file':'screenshots/'+f.name,'sha256':hashlib.sha256(data).hexdigest(),'width':w,'height':h})
(p/'probe-receipt.json').write_text(json.dumps({'appId':'tw.mars.stormapocalypse','actualUnsignedSimulator':True,'deviceName':'iPad Pro 13-inch (M4)','snapshots':records,'sourceUnmodified':True,'noSigning':True,'noStoreUpload':True,'loadedSceneRequiresVisualReview':True},indent=2)+'\n')
PY
