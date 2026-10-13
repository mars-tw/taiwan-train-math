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
cleanup() {
  local rc=$?
  trap - EXIT
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
[[ ! -e "$png" && ! -e "$output/title-simctl-raw.png" && ! -e "$result" ]] || { echo "Output already contains capture/result" >&2; exit 2; }
if find "$container_root" -type f \( -name seven-title-ready.txt -o -name seven-main001-ready.txt \) -print -quit | grep -q .; then
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

capture_phase() {
  local phase="$1"
  local marker_name expected png_path receipt_path ack_name marker=""
  if [[ "$phase" == title ]]; then
    marker_name=seven-title-ready.txt
    expected=phase=title
    png_path="$output/title-simctl-raw.png"
    receipt_path="$output/title-simctl-evidence.json"
    ack_name=seven-title-captured.flag
  else
    marker_name=seven-main001-ready.txt
    expected=mission=MAIN-001
    png_path="$png"
    receipt_path="$output/main001-simctl-evidence.json"
    ack_name=seven-main001-captured.flag
  fi
  for ((i=0; i<600; i++)); do
    marker="$(find "$container_root" -type f -name "$marker_name" -print -quit 2>/dev/null || true)"
    [[ -n "$marker" ]] && break
    if ! kill -0 "$test_pid" 2>/dev/null; then
      wait "$test_pid" || true
      echo "UI test exited before $phase marker; see $log and $result" >&2
      exit 1
    fi
    sleep 2
  done
  [[ -n "$marker" ]] || { echo "Timed out waiting for $phase marker" >&2; exit 1; }

  # XCTest remains active with the real Godot app foregrounded until we ack.
  xcrun simctl io "$device" screenshot --type=png "$png_path"
  python3 - "$png_path" "$marker" "$receipt_path" "$expected" <<'PY'
import hashlib, json, pathlib, struct, sys
png, marker, receipt = map(pathlib.Path, sys.argv[1:4])
expected = sys.argv[4]
raw = png.read_bytes()
if raw[:8] != b'\x89PNG\r\n\x1a\n' or len(raw) < 33:
    raise SystemExit('simctl did not create a valid PNG')
width, height = struct.unpack('>II', raw[16:24])
if width <= height:
    raise SystemExit(f'simctl screenshot is not landscape: {width}x{height}')
if expected not in marker.read_text(encoding='utf-8'):
    raise SystemExit(f'XCUITest did not certify the {expected} capture gate')
receipt.write_text(json.dumps({
    'source': 'xcrun simctl io <UDID> screenshot --type=png',
    'rawPng': png.name,
    'width': width,
    'height': height,
    'sha256': hashlib.sha256(raw).hexdigest(),
    'uiTestGate': marker.read_text(encoding='utf-8'),
    'visualReviewPending': True,
    'listingUploadReady': False,
}, indent=2) + '\n', encoding='utf-8')
PY
  touch "$(dirname "$marker")/$ack_name"
}

capture_phase title
capture_phase main001
wait "$test_pid"
test_pid=""
echo "UI test passed; raw title and MAIN-001 landscape simctl PNGs captured in $output"
