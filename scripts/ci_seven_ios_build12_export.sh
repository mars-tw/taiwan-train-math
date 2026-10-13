#!/bin/bash
# Godot-only macOS CI: no App Store upload; all private data stays in owned temp.
set +x
set -euo pipefail
umask 077
phase="${1:?prepare, sim or sign required}"
source_root="${2:?verified extracted source root required}"
project="${3:?explicit Godot project required}"
out="${4:?public artifact directory required}"
metadata="${5:?pinned source hash metadata required}"
tools="$(cd "$(dirname "$0")" && pwd)"
verify="$tools/ci_verify_seven_build12.py"
[[ "$(uname -s)" == Darwin && -n "${RUNNER_TEMP:-}" && -f "$verify" ]] || { echo 'macOS runner/tools required'; exit 2; }
case "$project" in
  seven-district-reckoning) app_id='tw.mars.sevendistrictreckoning'; name='SevenDistrict' ;;
  *) echo 'Unknown Godot project'; exit 2 ;;
esac
source_root="$(cd "$source_root" && pwd)"
mkdir -p "$out"; out="$(cd "$out" && pwd)"
scratch="$(mktemp -d "$RUNNER_TEMP/godot-ios-$project-$phase.XXXXXXXX")"
keychain=''; owned_profiles=(); devices=()
cleanup() {
  status=$?
  trap - EXIT INT TERM
  set +e
  for device in ${devices[@]+"${devices[@]}"}; do
    if [[ "$device" =~ ^[A-Fa-f0-9-]{36}$ ]]; then xcrun simctl shutdown "$device" >/dev/null 2>&1; xcrun simctl delete "$device" >/dev/null 2>&1; fi
  done
  if [[ -f "$scratch/keychains-before.json" ]]; then
    python3 - "$scratch/keychains-before.json" <<'PY'
import json,subprocess,sys
subprocess.run(['security','list-keychains','-d','user','-s',*json.load(open(sys.argv[1]))],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
PY
  fi
  [[ -z "$keychain" ]] || security delete-keychain "$keychain" >/dev/null 2>&1
  for profile in ${owned_profiles[@]+"${owned_profiles[@]}"}; do rm -f "$profile"; done
  if [[ -f "$scratch/profiles-owned.json" ]]; then
    python3 - "$scratch/profiles-owned.json" <<'PY'
import json,pathlib,sys
for name in json.load(open(sys.argv[1])):pathlib.Path(name).unlink(missing_ok=True)
PY
  fi
  python3 - "$scratch" "$RUNNER_TEMP" <<'PY'
import pathlib,shutil,sys
target=pathlib.Path(sys.argv[1]).resolve();parent=pathlib.Path(sys.argv[2]).resolve()
if target!=parent and target.is_relative_to(parent) and target.name.startswith('godot-ios-'):shutil.rmtree(target,ignore_errors=True)
PY
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
safe_cmd() {
  label="$1"; limit="$2"; shift 2
  python3 - "$scratch/$label.log" "$limit" "$phase" "$label" "$out" "$project" "$@" <<'PY'
import json,pathlib,re,subprocess,sys
log_path=pathlib.Path(sys.argv[1]);timed_out=False;exit_code=None
try:
 with log_path.open('wb') as log:
  result=subprocess.run(sys.argv[7:],stdout=log,stderr=subprocess.STDOUT,timeout=int(sys.argv[2]))
  exit_code=result.returncode
except subprocess.TimeoutExpired:timed_out=True
except OSError:pass
if exit_code==0:raise SystemExit(0)
# Only the unsigned Simulator compiler runs before the signing secret step.
# Publish a bounded diagnostic summary, never raw logs or signing output.
if sys.argv[3:5]==['sim','sim-build']:
 diagnostics=[]
 if log_path.exists():
  with log_path.open('rb') as log:
   log.seek(max(0,log_path.stat().st_size-8*1024*1024))
   lines=log.read().decode('utf-8','replace').splitlines()
  following=0
  for line in lines:
   line=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',line).strip()
   match=re.search(r'\b(?:fatal )?error:|^ld:|Undefined symbols for architecture|\*\* BUILD FAILED \*\*',line)
   if 'Undefined symbols for architecture' in line:following=8
   elif following:following-=1
   if not match and not following:continue
   line=re.sub(r'/(?:Users|private|var|Volumes|home)/[^\s\"\'<>]+','<path>',line)
   line=re.sub(r'[\x00-\x1f\x7f]',' ',line)[:500]
   if line and line not in diagnostics:diagnostics.append(line)
   if len(diagnostics)>=20:break
 report={'projectId':sys.argv[6],'phase':'sim-build','exitCode':exit_code,'timedOut':timed_out,'diagnostics':diagnostics,'rawLogsUploaded':False,'macBuildCompleted':False,'simulatorExecuted':False,'signatureVerified':False,'storeUploadPerformed':False}
 (pathlib.Path(sys.argv[5])/'sim-build-failure.json').write_text(json.dumps(report,indent=2))
 print(json.dumps(report))
raise SystemExit('Godot CI command failed; raw/private logs are not uploaded')
PY
}
clean_cmd() { env -u APPLE_DISTRIBUTION_P12_BASE64 -u APPLE_DISTRIBUTION_P12_PASSWORD -u APPLE_APPSTORE_PROFILE_BASE64 "$@"; }
python3 "$verify" source --root "$source_root" --metadata "$metadata" --project "$project" --output "$out/source-verification.json"
clean_cmd xcodebuild -version > "$scratch/xcode.txt"
python3 - "$scratch/xcode.txt" <<'PY'
import pathlib,re,sys
if not re.fullmatch(r'Xcode 26\.3\s+Build version 17C529\s*',pathlib.Path(sys.argv[1]).read_text().strip()):raise SystemExit('Exact Xcode 26.3/17C529 required')
PY
if [[ "$phase" == prepare ]]; then echo "Verified $project source; Mac build/sign/simulator not performed in prepare."; exit 0; fi

if [[ "$phase" == sim ]]; then
  [[ "$(uname -m)" == x86_64 ]] || { echo 'The verified Godot x86_64 Simulator library requires the actual Intel runner'; exit 2; }
  python3 - "$source_root" "$name" "$out" "$project" <<'PY'
import hashlib,json,pathlib,platform,subprocess,sys
root=pathlib.Path(sys.argv[1]);libraries=[]
for slice_name,expected in [('ios-arm64','arm64'),('ios-arm64_x86_64-simulator','x86_64')]:
 library=root/(sys.argv[2]+'.xcframework')/slice_name/'libgodot.a'
 result=subprocess.run(['xcrun','lipo','-archs',str(library)],capture_output=True,text=True,timeout=60)
 if result.returncode or result.stdout.split()!=[expected]:raise SystemExit('Actual Godot library architecture differs from the verified export recipe')
 libraries.append({'slice':slice_name,'actualArchitecture':expected,'sha256':hashlib.sha256(library.read_bytes()).hexdigest()})
if platform.machine()!='x86_64':raise SystemExit('Actual Intel Simulator host required')
(pathlib.Path(sys.argv[3])/'simulator-architecture.json').write_text(json.dumps({'projectId':sys.argv[4],'runnerArchitecture':'x86_64','simulatorArchitecture':'x86_64','deviceArchitecture':'arm64','libraries':libraries,'sourceFilesChanged':False},indent=2))
PY
  safe_cmd sim-build 2400 xcodebuild -project "$source_root/$name.xcodeproj" -scheme "$name" -configuration Debug -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' -derivedDataPath "$scratch/derived-sim" CODE_SIGNING_ALLOWED=NO ONLY_ACTIVE_ARCH=NO ARCHS=x86_64 EXCLUDED_ARCHS=arm64 build
  app="$scratch/derived-sim/Build/Products/Debug-iphonesimulator/$name.app"
  python3 "$verify" app --root "$source_root" --project "$project" --app "$app" --output "$out/simulator-verification.json"
  xcrun simctl list --json > "$scratch/inventory.json"
  python3 - "$scratch" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1]);inventory=json.loads((p/'inventory.json').read_text())
runtimes=[r for r in inventory['runtimes'] if r.get('isAvailable') is True and not r.get('availabilityError') and r['identifier'].startswith('com.apple.CoreSimulator.SimRuntime.iOS-') and r['version'].split('.')[0]=='26']
runtimes.sort(key=lambda r:tuple(map(int,r['version'].split('.'))),reverse=True)
phone=[d for d in inventory['devicetypes'] if d['name']=='iPhone 17 Pro Max']
tablet=[d for d in inventory['devicetypes'] if d['name'].startswith('iPad Pro 13-inch (M4)')]
tablet.sort(key=lambda d:('16GB' not in d['name'],d['name']))
if not runtimes or len(phone)!=1 or not tablet:raise SystemExit('Actual iPhone17ProMax/iPadM4/iOS26 runtime unavailable')
runtime=runtimes[0];encoded=int(runtime['version'].split('.')[0])*65536+int(runtime['version'].split('.')[1])*256
for model in [phone[0],tablet[0]]:
 if not model.get('minRuntimeVersion',0)<=encoded<=model.get('maxRuntimeVersion',0xffffffff):raise SystemExit('Required actual model is incompatible with available runtime')
for field,value in [('runtime',runtime['identifier']),('phone-type',phone[0]['identifier']),('tablet-type',tablet[0]['identifier'])]:(p/field).write_text(value)
(p/'models.json').write_text(json.dumps({'runtime':runtime['version'],'iphone':phone[0]['name'],'ipad':tablet[0]['name']}))
(p/'previous-devices.json').write_text(json.dumps([d['udid'].lower() for group in inventory.get('devices',{}).values() for d in group]))
PY
  runtime="$(cat "$scratch/runtime")"
  for kind in iphone ipad; do
    if [[ "$kind" == iphone ]]; then model="$(cat "$scratch/phone-type")"; else model="$(cat "$scratch/tablet-type")"; fi
    device="$(xcrun simctl create "Mars-Godot-$project-${GITHUB_RUN_ID:-local}-$kind" "$model" "$runtime")"
    python3 - "$device" "$scratch/previous-devices.json" <<'PY'
import json,re,sys
if not re.fullmatch(r'[A-Fa-f0-9]{8}(?:-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}',sys.argv[1]) or sys.argv[1].lower() in json.load(open(sys.argv[2])):raise SystemExit('Not a new owned Simulator UUID')
PY
    devices+=("$device")
    safe_cmd "$kind-boot" 180 xcrun simctl boot "$device"
    safe_cmd "$kind-bootstatus" 600 xcrun simctl bootstatus "$device" -b
    safe_cmd "$kind-status" 60 xcrun simctl status_bar "$device" override --time 9:41 --batteryState charged --batteryLevel 100
    safe_cmd "$kind-install" 360 xcrun simctl install "$device" "$app"
    safe_cmd "$kind-launch" 360 xcrun simctl launch "$device" "$app_id"
    sleep 30
    safe_cmd "$kind-cold-capture" 120 xcrun simctl io "$device" screenshot --type=png "$scratch/$kind-cold.png"
    safe_cmd "$kind-terminate" 120 xcrun simctl terminate "$device" "$app_id"
    safe_cmd "$kind-relaunch" 360 xcrun simctl launch "$device" "$app_id"
    sleep 12
    safe_cmd "$kind-warm-capture" 120 xcrun simctl io "$device" screenshot --type=png "$scratch/$kind-relaunch.png"
    safe_cmd "$kind-shutdown" 60 xcrun simctl shutdown "$device"
  done
  cat > "$scratch/rgb.swift" <<'SWIFT'
import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
func stop() -> Never { fputs("RGB conversion failed\n",stderr);exit(1) }
let input=URL(fileURLWithPath:CommandLine.arguments[1]);let output=URL(fileURLWithPath:CommandLine.arguments[2])
let width=Int(CommandLine.arguments[3])!;let height=Int(CommandLine.arguments[4])!
guard let source=CGImageSourceCreateWithURL(input as CFURL,nil),let image=CGImageSourceCreateImageAtIndex(source,0,nil),
      (image.width==width && image.height==height) || (image.width==height && image.height==width) else {stop()}
guard let canvas=CGContext(data:nil,width:image.width,height:image.height,bitsPerComponent:8,bytesPerRow:image.width*4,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.noneSkipLast.rawValue) else {stop()}
canvas.interpolationQuality = .none
canvas.draw(image,in:CGRect(x:0,y:0,width:CGFloat(image.width),height:CGFloat(image.height)))
guard let rgb=canvas.makeImage(),let destination=CGImageDestinationCreateWithURL(output as CFURL,UTType.png.identifier as CFString,1,nil) else {stop()}
CGImageDestinationAddImage(destination,rgb,nil);guard CGImageDestinationFinalize(destination) else {stop()}
SWIFT
  mkdir -p "$out/screenshots"
  for kind in iphone ipad; do
    if [[ "$kind" == iphone ]]; then width=1320; height=2868; else width=2064; height=2752; fi
    for moment in cold relaunch; do safe_cmd "$kind-$moment-rgb" 180 xcrun swift "$scratch/rgb.swift" "$scratch/$kind-$moment.png" "$out/screenshots/$kind-$moment.png" "$width" "$height"; done
  done
  python3 - "$out" "$project" "$scratch/models.json" <<'PY'
import hashlib,json,pathlib,struct,sys
out=pathlib.Path(sys.argv[1]);shots=[]
for p in sorted((out/'screenshots').glob('*.png')):
 raw=p.read_bytes();size=struct.unpack('>II',raw[16:24]);expected=(1320,2868) if p.name.startswith('iphone') else (2064,2752)
 if raw[:8]!=b'\x89PNG\r\n\x1a\n' or size not in (expected,expected[::-1]) or raw[25]!=2:raise SystemExit('Actual RGB screenshot dimensions mismatch; no resizing allowed')
 shots.append({'file':'screenshots/'+p.name,'width':size[0],'height':size[1],'sha256':hashlib.sha256(raw).hexdigest()})
(out/'simulator-launch.json').write_text(json.dumps({'projectId':sys.argv[2],**json.load(open(sys.argv[3])),'actualSimulator':True,'simulatorArchitecture':'x86_64','runnerArchitecture':'x86_64','freshDevices':True,'screenshots':shots,'macBuildPerformed':True,'interactiveGameplayTested':False,'physicalDeviceTested':False,'speakerOutputTested':False,'loadedSceneRequiresVisualReview':True,'storeUploadPerformed':False},indent=2))
PY
  echo "Actual Simulator captures created for $project; visual review remains required."
  exit 0
fi

[[ "$phase" == sign ]] || { echo 'Unknown Godot export phase'; exit 2; }
for variable in APPLE_DISTRIBUTION_P12_BASE64 APPLE_DISTRIBUTION_P12_PASSWORD APPLE_APPSTORE_PROFILE_BASE64 APPLE_TEAM_ID; do
  [[ -n "${!variable:-}" ]] || { echo 'Per-App signing environment incomplete'; exit 2; }
done
export GODOT_CI_PRIVATE="$scratch"
python3 - <<'PY'
import base64,os,pathlib,re
if not re.fullmatch(r'[A-Z0-9]{10}',os.environ['APPLE_TEAM_ID']):raise SystemExit('Invalid expected Team')
root=pathlib.Path(os.environ['GODOT_CI_PRIVATE'])
for filename,key in [('distribution.p12','APPLE_DISTRIBUTION_P12_BASE64'),('app.mobileprovision','APPLE_APPSTORE_PROFILE_BASE64')]:
 data=base64.b64decode(''.join(os.environ[key].split()),validate=True)
 if not 0<len(data)<2*1024*1024:raise SystemExit('Invalid signing material size')
 with (root/filename).open('xb') as out:out.write(data)
 (root/filename).chmod(0o600)
PY
python3 "$verify" profile --project "$project" --profile "$scratch/app.mobileprovision" --output "$scratch/profile.json"
keychain="$scratch/signing.keychain-db"
export GODOT_CI_KEYCHAIN="$keychain"
python3 - <<'PY'
import json,os,pathlib,secrets,shlex,subprocess
root=pathlib.Path(os.environ['GODOT_CI_PRIVATE']);keychain=os.environ['GODOT_CI_KEYCHAIN'];password=secrets.token_hex(32)
def command(args):
 try:result=subprocess.run(args,capture_output=True,timeout=120)
 except (OSError,subprocess.TimeoutExpired):raise SystemExit('Private keychain command failed; output withheld') from None
 if result.returncode:raise SystemExit('Private keychain command failed; output withheld')
 return result.stdout.decode()
previous=shlex.split(command(['security','list-keychains','-d','user']))
(root/'keychains-before.json').write_text(json.dumps(previous))
command(['security','create-keychain','-p',password,keychain]);command(['security','set-keychain-settings','-lut','3600',keychain]);command(['security','unlock-keychain','-p',password,keychain])
command(['security','import',str(root/'distribution.p12'),'-k',keychain,'-P',os.environ['APPLE_DISTRIBUTION_P12_PASSWORD'],'-T','/usr/bin/codesign','-T','/usr/bin/security'])
command(['security','set-key-partition-list','-S','apple-tool:,apple:,codesign:','-s','-k',password,keychain]);command(['security','list-keychains','-d','user','-s',keychain,*previous])
expected=json.loads((root/'profile.json').read_text())['certificateSha1']
if expected not in command(['security','find-identity','-v','-p','codesigning',keychain]):raise SystemExit('P12 private identity does not match the supplied profile')
PY
unset APPLE_DISTRIBUTION_P12_BASE64 APPLE_DISTRIBUTION_P12_PASSWORD APPLE_APPSTORE_PROFILE_BASE64
uuid="$(python3 -c 'import json,os;print(json.load(open(os.environ["GODOT_CI_PRIVATE"]+"/profile.json"))["uuid"])')"
for directory in "$HOME/Library/MobileDevice/Provisioning Profiles" "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"; do
  destination="$directory/$uuid.mobileprovision"
  [[ ! -e "$destination" ]] || { echo 'Existing profile would be overwritten; refusing'; exit 2; }
  mkdir -p "$directory"
  python3 - "$scratch" "$destination" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]);destination=pathlib.Path(sys.argv[2]);record=root/'profiles-owned.json'
with destination.open('xb') as out:
 owned=json.loads(record.read_text()) if record.exists() else []
 record.write_text(json.dumps([*owned,str(destination)]))
 out.write((root/'app.mobileprovision').read_bytes())
destination.chmod(0o600)
PY
done
safe_cmd private-source-copy 180 ditto "$source_root" "$scratch/sign-source"
python3 "$verify" configure --root "$scratch/sign-source" --project "$project" --profile-details "$scratch/profile.json" --keychain "$keychain"
safe_cmd device-archive 2400 xcodebuild -project "$scratch/sign-source/$name.xcodeproj" -scheme "$name" -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' -archivePath "$scratch/$name.xcarchive" -derivedDataPath "$scratch/derived-device" archive
python3 - "$scratch" "$app_id" <<'PY'
import json,os,pathlib,plistlib,sys
root=pathlib.Path(sys.argv[1]);profile=json.loads((root/'profile.json').read_text())
options={'method':'app-store-connect','destination':'export','signingStyle':'manual','teamID':os.environ['APPLE_TEAM_ID'],'signingCertificate':profile['certificateSha1'],'provisioningProfiles':{sys.argv[2]:profile['name']},'uploadSymbols':False,'manageAppVersionAndBuildNumber':False}
(root/'ExportOptions.plist').write_bytes(plistlib.dumps(options))
PY
safe_cmd ipa-export 1200 xcodebuild -exportArchive -archivePath "$scratch/$name.xcarchive" -exportPath "$scratch/export" -exportOptionsPlist "$scratch/ExportOptions.plist"
ipas=("$scratch/export/"*.ipa)
[[ "${#ipas[@]}" == 1 && -f "${ipas[0]}" ]] || { echo 'Expected one exported IPA'; exit 2; }
python3 "$verify" ipa --root "$source_root" --project "$project" --profile "$scratch/app.mobileprovision" --ipa "${ipas[0]}" --output "$out/verification.json"
cp "${ipas[0]}" "$out/signed.ipa"
echo "Signed Godot IPA verified for $project; no store upload or approval claimed."
