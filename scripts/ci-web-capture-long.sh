#!/bin/bash
# Unsigned capture only. Uses approved source/verifier; signing helper/tag remain frozen.
# Cold30/warm60 waits follow actual Pro Max startup probe; no UI resizing.
set -euo pipefail
phase="${1:?sim required}"
[[ "$phase" == sim ]] || { echo "Unsigned capture only"; exit 2; }
app="${2:?flat extracted app directory required}"
project="${3:?explicit project ID required}"
out="${4:?public artifact directory required}"
tools="${CI_TOOLS:?approved source helper folder required}"
verify="$tools/ci_verify_ios.py"
[[ "$(uname -s)" == Darwin ]] || { echo 'macOS runner required'; exit 2; }
[[ "$project" =~ ^[a-z0-9-]+$ ]] || exit 2
[[ -d "$app" && -f "$verify" && -n "${RUNNER_TEMP:-}" ]] || exit 2
app="$(cd "$app" && pwd)"
mkdir -p "$out"; out="$(cd "$out" && pwd)"
scratch="$(mktemp -d "$RUNNER_TEMP/ios-$project-$phase.XXXXXX")"
keychain=""; installed_profile=""; phone=""; tablet=""

cleanup() {
  set +e
  for device in "$phone" "$tablet"; do
    if [[ "$device" =~ ^[A-Fa-f0-9-]{36}$ ]]; then xcrun simctl shutdown "$device" >/dev/null 2>&1; xcrun simctl delete "$device" >/dev/null 2>&1; fi
  done
  if [[ -f "$scratch/keychains-before.json" ]]; then
    python3 - "$scratch/keychains-before.json" <<'PY'
import json,subprocess,sys
subprocess.run(['security','list-keychains','-d','user','-s',*json.load(open(sys.argv[1]))],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
PY
  fi
  if [[ -n "$keychain" && "$keychain" == "$scratch/"* ]]; then security delete-keychain "$keychain" >/dev/null 2>&1; fi
  if [[ -n "$installed_profile" && -f "$scratch/profile-installed" ]]; then rm -f "$installed_profile"; fi
  python3 - "$scratch" "$RUNNER_TEMP" <<'PY'
import pathlib,shutil,sys
target=pathlib.Path(sys.argv[1]).resolve();root=pathlib.Path(sys.argv[2]).resolve()
if target != root and target.is_relative_to(root) and target.name.startswith('ios-'):
    shutil.rmtree(target,ignore_errors=True)
PY
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

safe_cmd() {
  label="$1"; shift
  python3 - "$scratch/$label.log" "$@" <<'PY'
import pathlib,subprocess,sys
try:
    with pathlib.Path(sys.argv[1]).open('wb') as log:
        result=subprocess.run(sys.argv[2:],stdout=log,stderr=subprocess.STDOUT,timeout=2400)
except (OSError,subprocess.TimeoutExpired):
    raise SystemExit('Native build command could not finish; command/private output withheld') from None
if result.returncode:raise SystemExit('Native build command failed at '+pathlib.Path(sys.argv[1]).stem+'; private logs are not printed or uploaded')
PY
}

verify_phase() {
  local mode="$1"; shift
  case "$mode" in source|app|profile|ipa) ;; *) return 2 ;; esac
  echo "Public verification phase: $mode"
  if ! python3 "$verify" "$mode" "$@"; then
    echo "Verification phase failed: $mode; private inputs/tool output remain withheld"
    return 2
  fi
}

verify_phase source --root "$app" --project "$project" --output "$out/source-verification.json"
xcodebuild -version > "$scratch/xcode-version.txt"
grep -q '^Xcode 26\.3$' "$scratch/xcode-version.txt" || { echo 'Pinned Xcode 26.3 is required'; exit 2; }

if [[ "$phase" == prepare ]]; then
  cd "$app"
  safe_cmd npm-ci npm ci
  safe_cmd cap-sync-ios npx --no-install cap sync ios
  verify_phase source --root "$app" --project "$project" --output "$out/source-verification.json"
  # Synchronization must retain the explicitly configured deployment/resources.
  echo "Prepared and verified $project"
  exit 0
fi

if [[ "$phase" == sim ]]; then
  cd "$app"
  safe_cmd simulator-build xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Debug -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' -derivedDataPath "$scratch/derived-sim" CODE_SIGNING_ALLOWED=NO ONLY_ACTIVE_ARCH=NO build
  simulator_app="$scratch/derived-sim/Build/Products/Debug-iphonesimulator/App.app"
  verify_phase app --root "$app" --project "$project" --app "$simulator_app" --output "$out/simulator-verification.json"
  xcrun simctl list runtimes -j > "$scratch/runtimes.json"
  xcrun simctl list devicetypes -j > "$scratch/devices.json"
  python3 - "$scratch" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]);r=json.loads((p/'runtimes.json').read_text());d=json.loads((p/'devices.json').read_text())
runtime=[x for x in r['runtimes'] if x.get('isAvailable') and x['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-') and x['version'].split('.')[0]=='26']
runtime.sort(key=lambda x:tuple(int(a) for a in x['version'].split('.')),reverse=True)
phones=[x for x in d['devicetypes'] if x['name']=='iPhone 17 Pro Max']
pads=[x for x in d['devicetypes'] if x['name'].startswith('iPad Pro 13-inch (M4)')]
pads.sort(key=lambda x:('16GB' not in x['name'],x['name']))
if not runtime or len(phones)!=1 or not pads:raise SystemExit('Required iOS 26 runtime/iPhone17ProMax/iPadM4 are unavailable')
for name,value in [('runtime',runtime[0]['identifier']),('phone-type',phones[0]['identifier']),('tablet-type',pads[0]['identifier']),('phone-name',phones[0]['name']),('tablet-name',pads[0]['name']),('runtime-version',runtime[0]['version'])]:
 (p/name).write_text(value)
PY
  runtime="$(cat "$scratch/runtime")"
  phone="$(xcrun simctl create "Mars-$project-${GITHUB_RUN_ID:-local}-iphone" "$(cat "$scratch/phone-type")" "$runtime")"
  tablet="$(xcrun simctl create "Mars-$project-${GITHUB_RUN_ID:-local}-ipad" "$(cat "$scratch/tablet-type")" "$runtime")"
  app_id="$(python3 - "$app/capacitor.config.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['appId'])
PY
)"
  mkdir -p "$out/screenshots"
  for kind in iphone ipad; do
    if [[ "$kind" == iphone ]]; then device="$phone"; else device="$tablet"; fi
    safe_cmd "$kind-boot" xcrun simctl boot "$device"
    python3 - "$device" <<'PY'
import subprocess,sys
try:p=subprocess.run(['xcrun','simctl','bootstatus',sys.argv[1],'-b'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=300)
except (OSError,subprocess.TimeoutExpired):raise SystemExit('Fresh simulator boot timed out') from None
if p.returncode:raise SystemExit('Fresh simulator boot did not complete')
PY
    safe_cmd "$kind-statusbar" xcrun simctl status_bar "$device" override --time 9:41 --dataNetwork wifi --wifiMode active --wifiBars 3 --batteryState charged --batteryLevel 100
    safe_cmd "$kind-install" xcrun simctl install "$device" "$simulator_app"
    safe_cmd "$kind-launch" xcrun simctl launch "$device" "$app_id"
    sleep 30
    safe_cmd "$kind-cold-shot" xcrun simctl io "$device" screenshot --type=png "$scratch/$kind-cold.png"
    safe_cmd "$kind-terminate" xcrun simctl terminate "$device" "$app_id"
    safe_cmd "$kind-relaunch" xcrun simctl launch "$device" "$app_id"
    sleep 60
    safe_cmd "$kind-relaunch-shot" xcrun simctl io "$device" screenshot --type=png "$scratch/$kind-relaunch.png"
    safe_cmd "$kind-shutdown" xcrun simctl shutdown "$device"
  done
  cd "$app"
  SCREENSHOT_INPUT="$scratch" SCREENSHOT_OUTPUT="$out/screenshots" node --input-type=module <<'JS'
import sharp from 'sharp';import path from 'node:path';
for(const device of ['iphone','ipad'])for(const moment of ['cold','relaunch']){
 const source=path.join(process.env.SCREENSHOT_INPUT,`${device}-${moment}.png`);
 const expected=device==='iphone'?[1320,2868]:[2064,2752];
 const meta=await sharp(source).metadata();
 if(meta.width!==expected[0]||meta.height!==expected[1])throw Error('Simulator capture dimensions differ from selected devices');
 await sharp(source).removeAlpha().png({palette:false}).toFile(path.join(process.env.SCREENSHOT_OUTPUT,`${device}-${moment}.png`));
}
JS
  python3 - "$out" "$project" "$scratch" <<'PY'
import hashlib,json,pathlib,struct,sys
p=pathlib.Path(sys.argv[1]);devices=pathlib.Path(sys.argv[3]);shots=[]
for f in sorted((p/'screenshots').glob('*.png')):
 data=f.read_bytes();w,h=struct.unpack('>II',data[16:24])
 if data[25]!=2:raise SystemExit('Store screenshots must be RGB without alpha')
 kind='iphone' if f.name.startswith('iphone-') else 'ipad'
 device_name=(devices/('phone-name' if kind=='iphone' else 'tablet-name')).read_text()
 shots.append({'file':'screenshots/'+f.name,'deviceName':device_name,'width':w,'height':h,'nativeResolution':True,'uiResized':False,'sha256':hashlib.sha256(data).hexdigest()})
(p/'simulator-launch.json').write_text(json.dumps({'projectId':sys.argv[2],'captureHelperRevision':'repository-unsigned-capture-warm60','phoneDeviceName':(devices/'phone-name').read_text(),'tabletDeviceName':(devices/'tablet-name').read_text(),'iosRuntimeVersion':(devices/'runtime-version').read_text(),'actualSimulator':True,'freshDevices':True,'coldLaunchWaitSeconds':30,'relaunchWaitSeconds':60,'screenshots':shots,'interactiveGameplayTested':False,'physicalDeviceTested':False,'speakerOutputTested':False,'loadedSceneRequiresVisualReview':True},indent=2)+'\n')
PY
  echo "Fresh iPhone/iPad capture finished for $project; loaded UI requires visual review"
  exit 0
fi

