#!/bin/bash
# Run only on a booted, fresh iOS Simulator containing the already verified
# SevenDistrict.app. The separate Xcode project never builds or installs it.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: run_probe.sh <fresh-booted-simulator-UDID> <output-directory>" >&2
  exit 2
fi
device="$1"
output="$2"
if [[ ! "$device" =~ ^[0-9A-Fa-f]{8}-([0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}$ ]]; then
  echo "Invalid Simulator UDID" >&2
  exit 2
fi
mkdir -p "$output"
output="$(cd "$output" && pwd)"
probe_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
container_root="$HOME/Library/Developer/CoreSimulator/Devices/$device/data/Containers/Data/Application"
png="$output/main001-simctl-raw.png"
log="$output/xcodebuild-ui-test.log"
result="$output/SevenProbe.xcresult"
test_pid=""
current_phase="setup"
cleanup() {
  local rc=$?
  trap - EXIT
  if [[ "$rc" -ne 0 ]]; then
    python3 - "$output/probe-exit.json" "$current_phase" "$rc" <<'PY'
import json,pathlib,sys
path=pathlib.Path(sys.argv[1]);path.write_text(json.dumps({
 'phase':sys.argv[2],'exitCode':int(sys.argv[3]),'rawLogsPublished':False,
 'listingUploadReady':False,'storeUploadPerformed':False},indent=2)+'\n')
PY
  fi
  if [[ -n "$test_pid" ]]; then
    if kill -0 "$test_pid" 2>/dev/null; then
      kill "$test_pid" 2>/dev/null || true
    fi
    wait "$test_pid" 2>/dev/null || true
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[[ -d "$container_root" ]] || { echo "Simulator data container missing" >&2; exit 2; }
[[ ! -e "$png" && ! -e "$output/title-simctl-raw.png" && ! -e "$output/activated-simctl-raw.png" && ! -e "$result" ]] || { echo "Output already contains capture/result" >&2; exit 2; }
if find "$container_root" -type f \( -name seven-activated-ready.txt -o -name seven-title-ready.txt -o -name seven-main001-ready.txt \) -print -quit | grep -q .; then
  echo "Stale capture marker found; this must be a fresh Simulator" >&2
  exit 2
fi

# Xcode's test runner is built for this Intel macos-15 host. No Godot project,
# PCK, installed game binary, or signing setting is changed by this command.
xcodebuild \
  -project "$probe_root/SevenProbe.xcodeproj" \
  -scheme SevenProbe \
  -configuration Debug \
  -sdk iphonesimulator \
  -destination "platform=iOS Simulator,id=$device" \
  -derivedDataPath "$output/derived-probe" \
  -resultBundlePath "$result" \
  -parallel-testing-enabled NO \
  -maximum-concurrent-test-simulator-destinations 1 \
  CODE_SIGNING_ALLOWED=NO ARCHS=x86_64 EXCLUDED_ARCHS=arm64 \
  test >"$log" 2>&1 &
test_pid=$!

take_diagnostic() {
  local label="$1" path="$output/$1-simctl-raw.png" receipt="$output/$1-simctl-evidence.json"
  [[ ! -e "$path" ]] || return 0
  if ! xcrun simctl io "$device" screenshot --type=png "$path" >/dev/null 2>&1; then
    echo "Native diagnostic frame unavailable: $label" >&2
    return 0
  fi
  python3 - "$path" "$receipt" "$label" <<'PY'
import hashlib,json,pathlib,struct,sys
path,receipt=map(pathlib.Path,sys.argv[1:3]);raw=path.read_bytes()
if (len(raw)<26 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR'
    or not 0<len(raw)<=24*1024**2):raise SystemExit('Bounded native diagnostic PNG invalid')
width,height=struct.unpack('>II',raw[16:24])
if not 0<width<=4096 or not 0<height<=4096:raise SystemExit('Native diagnostic geometry unbounded')
receipt.write_text(json.dumps({'phase':sys.argv[3],'source':'xcrun simctl io <UDID> screenshot --type=png',
 'file':path.name,'width':width,'height':height,'bytes':len(raw),
 'sha256':hashlib.sha256(raw).hexdigest(),'listingCandidate':False,
 'storeUploadPerformed':False},indent=2)+'\n')
PY
}

capture_phase() {
  local phase="$1"
  local marker_name expected png_path ack_name marker="" xctest_source xctest_path
  current_phase="$phase"
  if [[ "$phase" == activated ]]; then
    marker_name=seven-activated-ready.txt
    expected=phase=activated
    png_path="$output/activated-simctl-raw.png"
    ack_name=seven-activated-captured.flag
  elif [[ "$phase" == title ]]; then
    marker_name=seven-title-ready.txt
    expected=phase=title
    png_path="$output/title-simctl-raw.png"
    ack_name=seven-title-captured.flag
  else
    marker_name=seven-main001-ready.txt
    expected=mission=MAIN-001
    png_path="$png"
    ack_name=seven-main001-captured.flag
  fi
  for ((i=0; i<360; i++)); do
    marker="$(find "$container_root" -type f -name "$marker_name" -print -quit 2>/dev/null || true)"
    [[ -n "$marker" ]] && break
    if [[ "$phase" == title ]]; then
      case "$i" in
        60) take_diagnostic title-wait-t120 ;;
        120) take_diagnostic title-wait-t240 ;;
        180) take_diagnostic title-wait-t360 ;;
      esac
    fi
    if ! kill -0 "$test_pid" 2>/dev/null; then
      wait "$test_pid" || true
      [[ "$phase" == activated ]] && take_diagnostic activation-failure
      [[ "$phase" == title ]] && take_diagnostic title-wait-final
      echo "UI test exited before $phase marker; see $log and $result" >&2
      exit 1
    fi
    sleep 2
  done
  if [[ -z "$marker" ]]; then
    [[ "$phase" == activated ]] && take_diagnostic activation-failure
    [[ "$phase" == title ]] && take_diagnostic title-wait-final
    echo "Timed out waiting for $phase marker" >&2
    exit 1
  fi

  # The UI test atomically wrote its unaltered PNG before announcing readiness.
  # Keep that original byte stream and a separate physical simctl screenshot.
  xctest_source="$(dirname "$marker")/seven-$phase-xctest.png"
  xctest_path="$output/$phase-xctest-raw.png"
  [[ -f "$xctest_source" && ! -L "$xctest_source" && ! -e "$xctest_path" ]] || {
    echo "XCTest raw $phase PNG missing or linked" >&2; exit 1;
  }
  cp "$xctest_source" "$xctest_path"
  xcrun simctl io "$device" screenshot --type=png "$png_path"
  python3 - "$png_path" "$xctest_path" "$marker" "$output" "$phase" "$expected" <<'PY'
import hashlib,json,pathlib,struct,sys
simctl,xctest,marker,output=map(pathlib.Path,sys.argv[1:5])
phase,gate=sys.argv[5:7]
marker_text=marker.read_text(encoding='utf-8')
if gate not in marker_text:raise SystemExit('XCUITest phase gate differs')
required=(2622,1206) if 'orientation=landscapeLeft' in marker_text else (
 (2752,2064) if 'orientation=landscapeRight' in marker_text else None)
if required is None:raise SystemExit('XCUITest physical orientation marker missing')
rows={}
for method,path,source in (
 ('simctl',simctl,'xcrun simctl io <UDID> screenshot --type=png'),
 ('xctest',xctest,'XCUIScreen.main.screenshot().pngRepresentation')):
 if not path.is_file() or path.is_symlink() or not 33<=path.stat().st_size<=24*1024**2:
  raise SystemExit('Missing or unbounded original '+method+' PNG')
 with path.open('rb') as stream:raw=stream.read()
 if raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR':
  raise SystemExit('Original '+method+' frame is not PNG')
 width,height=struct.unpack('>II',raw[16:24])
 if not 0<width<=4096 or not 0<height<=4096:
  raise SystemExit('Unbounded original '+method+' geometry')
 row={'source':source,'rawPng':path.name,'width':width,'height':height,
      'bytes':len(raw),'bitDepth':raw[24],'colorType':raw[25],
      'sha256':hashlib.sha256(raw).hexdigest(),'uiTestGate':marker_text,
      'nativeGeometryAccepted':(width,height)==required,
      'visualReviewPending':True,'listingUploadReady':False,
      'storeUploadPerformed':False}
 if method=='xctest' and (
     'xctestPNGFile=seven-'+phase+'-xctest.png' not in marker_text
     or 'xctestPNGBytes='+str(len(raw)) not in marker_text
     or 'xctestPNGSHA256='+row['sha256'] not in marker_text
     or 'xctestPNGIHDRPixels='+str(width)+','+str(height) not in marker_text):
  raise SystemExit('Original XCTest PNG does not match its atomic ready marker')
 (output/(phase+'-'+method+'-evidence.json')).write_text(json.dumps(row,indent=2)+'\n')
 rows[method]=row
chosen='simctl' if rows['simctl']['nativeGeometryAccepted'] else (
 'xctest' if rows['xctest']['nativeGeometryAccepted'] else None)
summary={'phase':phase,'requiredWidth':required[0],'requiredHeight':required[1],
 'chosenSource':chosen,'simctl':{k:rows['simctl'][k] for k in ('width','height','sha256','bytes')},
 'xctest':{k:rows['xctest'][k] for k in ('width','height','sha256','bytes')},
 'noRotateCropOrComposite':True,'listingUploadReady':False,'storeUploadPerformed':False}
(output/(phase+'-source-selection.json')).write_text(json.dumps(summary,indent=2)+'\n')
if chosen is None:
 raise SystemExit(f'Both original {phase} PNGs differ from native landscape: simctl={rows["simctl"]["width"]}x{rows["simctl"]["height"]} xctest={rows["xctest"]["width"]}x{rows["xctest"]["height"]}')
PY
  touch "$(dirname "$marker")/$ack_name"
}

capture_phase activated
capture_phase title
capture_phase main001
wait "$test_pid"
test_pid=""
echo "UI test passed; paired unaltered XCTest/simctl title and MAIN-001 PNGs captured in $output"
