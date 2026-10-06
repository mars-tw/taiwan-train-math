#!/usr/bin/env bash
# Template: macOS only; no tracing, private logs/artifacts, or automatic upload.
set +x
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/output/ios-store"
SOURCE="$ROOT/output/ios-store-source"
APP_ID='tw.mars.trainmath'
MODE="${1:-sign}"
TASK_TMP=''; KEYCHAIN=''; KEYCHAIN_ACTIVE=false; PREVIOUS_KEYCHAINS=(); INSTALLED_PROFILES=()
fail() { printf 'iOS store step stopped: %s\n' "$1" >&2; exit 1; }
cleanup() {
  local status=$?
  trap - EXIT INT TERM
  for profile in ${INSTALLED_PROFILES[@]+"${INSTALLED_PROFILES[@]}"}; do rm -f "$profile"; done
  if [ "$KEYCHAIN_ACTIVE" = true ]; then
    security list-keychains -d user -s ${PREVIOUS_KEYCHAINS[@]+"${PREVIOUS_KEYCHAINS[@]}"} >/dev/null 2>&1 || true
    security delete-keychain "$KEYCHAIN" >/dev/null 2>&1 || true
  fi
  if [ -n "$TASK_TMP" ] && [ -d "$TASK_TMP" ]; then
    case "$TASK_TMP" in "$TMP_BASE"/trainmath-ios-store.*) rm -rf "$TASK_TMP" ;; *) printf 'Refused unexpected cleanup path.\n' >&2 ;; esac
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
[ "$(uname -s)" = Darwin ] || fail 'requires macOS; this template does not run signing on Windows'
case "$MODE" in sign|upload) ;; *) fail 'choose sign or upload explicitly' ;; esac
for cmd in python3 security codesign openssl plutil ditto xcodebuild xcrun; do command -v "$cmd" >/dev/null || fail 'required Apple tool unavailable'; done
TMP_BASE="$(cd "${RUNNER_TEMP:-${TMPDIR:-/tmp}}" && pwd)"
TASK_TMP="$(mktemp -d "$TMP_BASE/trainmath-ios-store.XXXXXXXX")"
chmod 700 "$TASK_TMP"
mkdir -p "$OUT"
[ -n "${APPLE_TEAM_ID:-}" ] || fail 'missing APPLE_TEAM_ID'
python3 - <<'PY'
import os,re
if not re.fullmatch(r'[A-Z0-9]{10}',os.environ['APPLE_TEAM_ID']): raise SystemExit('Invalid team setting')
PY
clean_tool() { env -u APPLE_DISTRIBUTION_P12_BASE64 -u APPLE_DISTRIBUTION_P12_PASSWORD -u APPLE_APPSTORE_PROFILE_BASE64 -u ASC_PRIVATE_KEY_BASE64 "$@"; }
clean_tool xcodebuild -version >"$TASK_TMP/xcode.txt" 2>&1 || fail 'Xcode unavailable'
python3 - "$TASK_TMP/xcode.txt" <<'PY'
import pathlib,re,sys
if not re.fullmatch(r'Xcode 26\.3\s+Build version 17C529\s*',pathlib.Path(sys.argv[1]).read_text().strip()): raise SystemExit('Expected stable Xcode 26.3 / 17C529')
PY

# Reject traversal/escaping symlinks before ditto handles downloaded ZIPs.
check_zip() {
  python3 - "$1" <<'PY'
import pathlib,posixpath,stat,sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    if sum(i.file_size for i in archive.infolist())>2_000_000_000: raise SystemExit('Archive too large')
    for item in archive.infolist():
        path=pathlib.PurePosixPath(item.filename)
        if path.is_absolute() or '..' in path.parts or '\\' in item.filename: raise SystemExit('Unsafe ZIP path')
        if stat.S_ISLNK(item.external_attr>>16):
            target=archive.read(item).decode('utf8')
            resolved=posixpath.normpath(posixpath.join(str(path.parent),target))
            if target.startswith('/') or resolved=='..' or resolved.startswith('../'): raise SystemExit('Escaping ZIP symlink')
PY
}
check_resources() {
  python3 - "$1" "$SOURCE/bundle-manifest.json" <<'PY'
import hashlib,json,pathlib,plistlib,re,sys
app=pathlib.Path(sys.argv[1]); manifest=json.loads(pathlib.Path(sys.argv[2]).read_text())
info=plistlib.load(open(app/'Info.plist','rb'))
if info.get('CFBundleIdentifier')!='tw.mars.trainmath' or info.get('CFBundleShortVersionString')!='1.0.0' or info.get('CFBundleVersion')!='1': raise SystemExit('Rejected app identity/version/build')
if info.get('CFBundleSupportedPlatforms')!=['iPhoneOS'] or set(info.get('UIDeviceFamily',[]))!={1,2} or info.get('TestFlightInternalTestingOnly',False): raise SystemExit('Rejected device/platform/internal-only metadata')
if not re.fullmatch(r'iphoneos(?:2[6-9]|[3-9][0-9])(?:\.[0-9]+)*',info.get('DTSDKName','')) or info.get('DTXcodeBuild')!='17C529': raise SystemExit('Rejected archive SDK/compiler')
privacy=plistlib.load(open(app/'PrivacyInfo.xcprivacy','rb'))
if privacy.get('NSPrivacyTracking') is not False or not any(p.get('NSPrivacyAccessedAPIType')=='NSPrivacyAccessedAPICategoryUserDefaults' and 'CA92.1' in p.get('NSPrivacyAccessedAPITypeReasons',[]) for p in privacy.get('NSPrivacyAccessedAPITypes',[])): raise SystemExit('Rejected privacy manifest')
if manifest.get('appId')!='tw.mars.trainmath' or manifest.get('remoteServer') is not False or not isinstance(manifest.get('files'),list): raise SystemExit('Rejected native manifest')
public=(app/'public').resolve(); paths=set()
for item in manifest['files']:
    value=item.get('path',''); path=pathlib.PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value or value in paths: raise SystemExit('Unsafe manifest path')
    file=public/value
    if file.is_symlink() or not file.resolve().is_relative_to(public): raise SystemExit('Linked native resource')
    data=file.read_bytes()
    if len(data)!=item.get('bytes') or hashlib.sha256(data).hexdigest()!=item.get('sha256'): raise SystemExit('Native resource digest mismatch')
    paths.add(value)
required={'index.html','native-host.js','native-documents.js','native-ui.css','src/app.js','src/native-runtime.js','src/native-atomic-preferences.js','data/trains.json','privacy.html','support.html'}
if not required.issubset(paths): raise SystemExit('Missing native game resource')
trains=json.loads((public/'data/trains.json').read_text())['trains']
photos=[t['referencePhoto']['path'] for t in trains if t.get('referencePhoto',{}).get('status')=='verified']
if len(photos)!=58 or not all(path in paths for path in photos): raise SystemExit('Missing verified train photos')
config=json.loads((app/'capacitor.config.json').read_text()); server=config.get('server',{})
if config.get('appId')!='tw.mars.trainmath' or server.get('url') or server.get('cleartext') or server.get('hostname','localhost')!='localhost' or server.get('iosScheme','capacitor')!='capacitor': raise SystemExit('Unexpected native App ID/server configuration')
PY
}
verify_ipa() {
  local ipa="$1"
  check_zip "$ipa"
  ditto -x -k "$ipa" "$TASK_TMP/verify-ipa" >"$TASK_TMP/ipa-extract.log" 2>&1 || fail 'IPA extraction failed'
  local apps=("$TASK_TMP/verify-ipa/Payload/"*.app)
  [ "${#apps[@]}" -eq 1 ] && [ -d "${apps[0]}" ] || fail 'expected one device application'
  local app="${apps[0]}"
  codesign --verify --deep --strict -R='anchor apple generic' "$app" >"$TASK_TMP/signature.log" 2>&1 || fail 'invalid Apple-anchored code signature'
  security cms -D -i "$app/embedded.mobileprovision" >"$TASK_TMP/embedded.plist" 2>"$TASK_TMP/profile-decode.log" || fail 'embedded profile invalid'
  codesign -d --entitlements :- "$app" >"$TASK_TMP/entitlements.plist" 2>"$TASK_TMP/entitlements.log" || fail 'entitlements unavailable'
  codesign -dv --verbose=4 "$app" >"$TASK_TMP/identity.txt" 2>&1 || fail 'signature identity unavailable'
  codesign -d --extract-certificates="$TASK_TMP/cert" "$app" >"$TASK_TMP/cert.log" 2>&1 || fail 'certificate extraction failed'
  openssl x509 -inform DER -in "$TASK_TMP/cert0" -checkend 0 -noout >"$TASK_TMP/cert-expiry.log" 2>&1 || fail 'expired signing certificate'
  openssl x509 -inform DER -in "$TASK_TMP/cert0" -noout -subject -nameopt RFC2253 >"$TASK_TMP/cert-subject.txt" 2>"$TASK_TMP/cert-subject.log" || fail 'certificate subject unavailable'
  python3 - "$TASK_TMP/embedded.plist" "$TASK_TMP/entitlements.plist" "$TASK_TMP/identity.txt" "$TASK_TMP/cert0" "$TASK_TMP/profile.plist" "$TASK_TMP/cert-subject.txt" <<'PY'
import datetime,fnmatch,hashlib,os,pathlib,plistlib,re,sys
p=plistlib.load(open(sys.argv[1],'rb')); e=plistlib.load(open(sys.argv[2],'rb')); team=os.environ['APPLE_TEAM_ID']; pe=p.get('Entitlements',{})
if p.get('TeamIdentifier')!=[team] or pe.get('com.apple.developer.team-identifier')!=team or pe.get('application-identifier')!=team+'.tw.mars.trainmath' or e.get('application-identifier')!=team+'.tw.mars.trainmath' or e.get('com.apple.developer.team-identifier')!=team: raise SystemExit('Rejected profile/team/app entitlement')
supplied=pathlib.Path(sys.argv[5])
if supplied.is_file():
    expected=plistlib.load(open(supplied,'rb'))
    if p.get('UUID')!=expected.get('UUID') or p.get('Name')!=expected.get('Name'): raise SystemExit('Export did not embed the supplied profile')
subject=pathlib.Path(sys.argv[6]).read_text()
if not re.search(r'(?:^|,|subject=\s*)CN=Apple Distribution:',subject) or not re.search(r'(?:^|,|subject=\s*)OU='+team+r'(?:,|$)',subject): raise SystemExit('Rejected distribution certificate subject')
if pe.get('get-task-allow') is not False or pe.get('beta-reports-active') is not True or 'ProvisionedDevices' in p or p.get('ProvisionsAllDevices') or 'iOS' not in p.get('Platform',[]): raise SystemExit('Not an App Store profile')
if p['ExpirationDate'].replace(tzinfo=datetime.timezone.utc)<=datetime.datetime.now(datetime.timezone.utc): raise SystemExit('Expired profile')
if e.get('get-task-allow') is not False or e.get('beta-reports-active') is not True or ('TeamIdentifier='+team) not in open(sys.argv[3]).read(): raise SystemExit('Rejected release signing entitlements')
if hashlib.sha1(open(sys.argv[4],'rb').read()).digest() not in [hashlib.sha1(c).digest() for c in p.get('DeveloperCertificates',[])]: raise SystemExit('Profile/certificate mismatch')
def permitted(value,allowed):
    if isinstance(value,bool): return isinstance(allowed,bool) and value==allowed
    if isinstance(value,str): return isinstance(allowed,str) and fnmatch.fnmatchcase(value,allowed)
    if isinstance(value,list): return isinstance(allowed,list) and all(any(permitted(v,a) for a in allowed) for v in value)
    if isinstance(value,dict): return isinstance(allowed,dict) and all(k in allowed and permitted(v,allowed[k]) for k,v in value.items())
    return value==allowed
if not all(k in pe and permitted(v,pe[k]) for k,v in e.items()): raise SystemExit('Entitlements exceed supplied profile')
PY
  check_resources "$app"
}

if [ "$MODE" = upload ]; then
  for name in ASC_ISSUER_ID ASC_KEY_ID ASC_PRIVATE_KEY_BASE64; do [ -n "${!name:-}" ] || fail 'upload requested but ASC credentials are incomplete'; done
  python3 - "$OUT" <<'PY'
import hashlib,json,os,pathlib,re,sys
out=pathlib.Path(sys.argv[1]); report=json.loads((out/'verification.json').read_text())
if not re.fullmatch(r'[A-Z0-9]{10}',os.environ['ASC_KEY_ID']) or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',os.environ['ASC_ISSUER_ID']): raise SystemExit('Invalid ASC identifiers')
if report.get('bundleId')!='tw.mars.trainmath' or report.get('marketingVersion')!='1.0.0' or report.get('buildNumber')!='1' or report.get('signatureVerified') is not True or report.get('ipaSha256')!=hashlib.sha256((out/'TrainMath.ipa').read_bytes()).hexdigest(): raise SystemExit('IPA verification report mismatch')
PY
  verify_ipa "$OUT/TrainMath.ipa"
  mkdir -p "$TASK_TMP/private_keys"
  python3 - "$TASK_TMP/private_keys" <<'PY'
import base64,os,pathlib,sys
try: value=base64.b64decode(''.join(os.environ['ASC_PRIVATE_KEY_BASE64'].split()),validate=True)
except Exception: raise SystemExit('Invalid API key base64')
if not value.startswith(b'-----BEGIN PRIVATE KEY-----') or b'-----END PRIVATE KEY-----' not in value: raise SystemExit('Expected PEM p8 key')
(pathlib.Path(sys.argv[1])/('AuthKey_'+os.environ['ASC_KEY_ID']+'.p8')).write_bytes(value)
PY
  unset ASC_PRIVATE_KEY_BASE64
  openssl pkey -in "$TASK_TMP/private_keys/AuthKey_$ASC_KEY_ID.p8" -check -noout >"$TASK_TMP/key-check.log" 2>&1 || fail 'API key invalid'
  TRANSPORTER=''
  while IFS= read -r candidate; do [ ! -x "$candidate" ] || { TRANSPORTER="$candidate"; break; }; done < <(find "$DEVELOPER_DIR/../SharedFrameworks" -name iTMSTransporter -type f 2>/dev/null)
  [ -n "$TRANSPORTER" ] || fail 'official Xcode Transporter unavailable'
  cd "$TASK_TMP"
  for operation in verify upload; do
    if ! clean_tool "$TRANSPORTER" -m "$operation" -assetFile "$OUT/TrainMath.ipa" -apiKey "$ASC_KEY_ID" -apiIssuer "$ASC_ISSUER_ID" -v informational >"$TASK_TMP/$operation.log" 2>&1; then
      python3 - "$TASK_TMP/$operation.log" <<'PY'
import pathlib,re,sys
codes=sorted(set(re.findall(r'\bITMS-[0-9]+\b',pathlib.Path(sys.argv[1]).read_text(errors='replace'))))
print('Apple result codes: '+(', '.join(codes) if codes else 'authentication/network/tool failure'),file=sys.stderr)
PY
      fail 'Apple validation/upload failed; no success is claimed'
    fi
  done
  python3 - "$OUT" <<'PY'
import json,pathlib,sys
(pathlib.Path(sys.argv[1])/'upload-result.json').write_text(json.dumps({'appleValidationAccepted':True,'uploadCommandAccepted':True,'processingVerified':False,'testFlightAvailabilityVerified':False,'appStoreReviewApproved':False},indent=2))
PY
  printf 'Apple upload command accepted; processing and App Store review are unverified.\n'
  exit 0
fi

for name in APPLE_DISTRIBUTION_P12_BASE64 APPLE_DISTRIBUTION_P12_PASSWORD APPLE_APPSTORE_PROFILE_BASE64; do [ -n "${!name:-}" ] || fail 'signing credentials/profile incomplete'; done
[ ! -e "$OUT/TrainMath.ipa" ] || fail 'refusing to reuse existing signed output'
STRATEGY="${IOS_ARCHIVE_STRATEGY:-export-existing}"
case "$STRATEGY" in export-existing|signed-rearchive) ;; *) fail 'invalid archive strategy' ;; esac
check_zip "$SOURCE/TrainMath-unsigned.xcarchive.zip"
ditto -x -k "$SOURCE/TrainMath-unsigned.xcarchive.zip" "$TASK_TMP/input" >"$TASK_TMP/archive-extract.log" 2>&1 || fail 'archive extraction failed'
archives=("$TASK_TMP/input/"*.xcarchive)
[ "${#archives[@]}" -eq 1 ] && [ -d "${archives[0]}" ] || fail 'expected one unsigned device archive'
ARCHIVE="${archives[0]}"
check_resources "$ARCHIVE/Products/Applications/App.app"
python3 - "$TASK_TMP" <<'PY'
import base64,os,pathlib,sys
out=pathlib.Path(sys.argv[1])
for env,name in [('APPLE_DISTRIBUTION_P12_BASE64','distribution.p12'),('APPLE_APPSTORE_PROFILE_BASE64','distribution.mobileprovision')]:
    try: value=base64.b64decode(''.join(os.environ[env].split()),validate=True)
    except Exception: raise SystemExit('Invalid signing material base64')
    if not value: raise SystemExit('Empty signing material')
    (out/name).write_bytes(value)
PY
security cms -D -i "$TASK_TMP/distribution.mobileprovision" >"$TASK_TMP/profile.plist" 2>"$TASK_TMP/cms.log" || fail 'profile CMS decode failed'
python3 - "$TASK_TMP/profile.plist" <<'PY'
import datetime,os,plistlib,re,sys
p=plistlib.load(open(sys.argv[1],'rb')); e=p.get('Entitlements',{}); team=os.environ['APPLE_TEAM_ID']
if not re.fullmatch(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}',p.get('UUID','')) or not isinstance(p.get('Name'),str) or not p['Name']: raise SystemExit('Invalid profile identity')
if p.get('TeamIdentifier')!=[team] or e.get('com.apple.developer.team-identifier')!=team or e.get('application-identifier')!=team+'.tw.mars.trainmath': raise SystemExit('Profile is not for this team and explicit train-math App ID')
if e.get('get-task-allow') is not False or e.get('beta-reports-active') is not True or 'ProvisionedDevices' in p or p.get('ProvisionsAllDevices') or 'iOS' not in p.get('Platform',[]): raise SystemExit('Need an App Store distribution profile')
if p['ExpirationDate'].replace(tzinfo=datetime.timezone.utc)<=datetime.datetime.now(datetime.timezone.utc) or not p.get('DeveloperCertificates'): raise SystemExit('Profile expired or certificate unavailable')
PY
KEYCHAIN="$TASK_TMP/signing.keychain-db"
KEYCHAIN_PASSWORD="$(openssl rand -hex 32)"
while IFS= read -r value; do PREVIOUS_KEYCHAINS+=("$value"); done < <(security list-keychains -d user | python3 -c 'import shlex,sys;print("\n".join(shlex.split(sys.stdin.read())))')
security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN" >"$TASK_TMP/keychain.log" 2>&1 || fail 'temporary keychain creation failed'
KEYCHAIN_ACTIVE=true
security set-keychain-settings -lut 7200 "$KEYCHAIN" >>"$TASK_TMP/keychain.log" 2>&1
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN" >>"$TASK_TMP/keychain.log" 2>&1
security list-keychains -d user -s "$KEYCHAIN" ${PREVIOUS_KEYCHAINS[@]+"${PREVIOUS_KEYCHAINS[@]}"} >>"$TASK_TMP/keychain.log" 2>&1
security import "$TASK_TMP/distribution.p12" -k "$KEYCHAIN" -P "$APPLE_DISTRIBUTION_P12_PASSWORD" -T /usr/bin/codesign -T /usr/bin/security >"$TASK_TMP/import.log" 2>&1 || fail 'P12 import failed'
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN" >"$TASK_TMP/partition.log" 2>&1
unset APPLE_DISTRIBUTION_P12_BASE64 APPLE_DISTRIBUTION_P12_PASSWORD APPLE_APPSTORE_PROFILE_BASE64 KEYCHAIN_PASSWORD
security find-identity -v -p codesigning "$KEYCHAIN" >"$TASK_TMP/identities.txt" 2>&1
CERT_SHA="$(python3 - "$TASK_TMP" <<'PY'
import hashlib,pathlib,plistlib,re,sys
p=pathlib.Path(sys.argv[1]); profile=plistlib.load(open(p/'profile.plist','rb')); allowed={hashlib.sha1(c).hexdigest().upper() for c in profile['DeveloperCertificates']}
matches=[sha for sha,name in re.findall(r'^\s*\d+\)\s+([A-F0-9]{40})\s+"(Apple Distribution:[^"\n]+)"',(p/'identities.txt').read_text(),re.M) if sha in allowed]
if len(matches)!=1: raise SystemExit('Need one valid distribution identity covered by this profile')
print(matches[0])
PY
)"
PROFILE_UUID="$(python3 -c 'import plistlib,sys;print(plistlib.load(open(sys.argv[1],"rb"))["UUID"])' "$TASK_TMP/profile.plist")"
for folder in "$HOME/Library/MobileDevice/Provisioning Profiles" "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"; do
  mkdir -p "$folder"; destination="$folder/$PROFILE_UUID.mobileprovision"
  [ ! -e "$destination" ] || fail 'refusing to replace a pre-existing profile'
  INSTALLED_PROFILES+=("$destination"); cp "$TASK_TMP/distribution.mobileprovision" "$destination"
done
if [ "$STRATEGY" = signed-rearchive ]; then
  # Only this explicit mode recompiles the exact source-run App target.
  [ -d "$ROOT/source-archive/node_modules" ] || fail 'pinned source dependencies missing'
  mkdir -p "$TASK_TMP/work/ios"; ditto "$ROOT/source-archive/ios/App" "$TASK_TMP/work/ios/App"
  [ ! -f "$ROOT/source-archive/ios/debug.xcconfig" ] || cp "$ROOT/source-archive/ios/debug.xcconfig" "$TASK_TMP/work/ios/debug.xcconfig"
  ln -s "$ROOT/source-archive/node_modules" "$TASK_TMP/work/node_modules"
  ditto "$ARCHIVE/Products/Applications/App.app/public" "$TASK_TMP/work/ios/App/App/public"
  cp "$ARCHIVE/Products/Applications/App.app/PrivacyInfo.xcprivacy" "$TASK_TMP/work/ios/App/App/PrivacyInfo.xcprivacy"
  for resource in capacitor.config.json config.xml; do
    [ -f "$ARCHIVE/Products/Applications/App.app/$resource" ] || fail 'required generated native configuration missing from source archive'
    cp "$ARCHIVE/Products/Applications/App.app/$resource" "$TASK_TMP/work/ios/App/App/$resource"
  done
  PROJECT="$TASK_TMP/work/ios/App/App.xcodeproj"
  plutil -convert json -o "$TASK_TMP/project.json" "$PROJECT/project.pbxproj"
  python3 - "$PROJECT/project.pbxproj" "$TASK_TMP/project.json" "$PROFILE_UUID" "$CERT_SHA" <<'PY'
import json,os,pathlib,re,sys
path=pathlib.Path(sys.argv[1]); objects=json.load(open(sys.argv[2]))['objects']; text=path.read_text(); targets=[t for t in objects.values() if t.get('isa')=='PBXNativeTarget' and t.get('name')=='App' and t.get('productType')=='com.apple.product-type.application']
if len(targets)!=1: raise SystemExit('Expected one train-math App target')
settings={'CODE_SIGN_STYLE':'Manual','CODE_SIGN_IDENTITY':sys.argv[4],'DEVELOPMENT_TEAM':os.environ['APPLE_TEAM_ID'],'PROVISIONING_PROFILE_SPECIFIER':sys.argv[3],'MARKETING_VERSION':'1.0.0','CURRENT_PROJECT_VERSION':'1'}
for cid in objects[targets[0]['buildConfigurationList']]['buildConfigurations']:
    if objects[cid]['buildSettings'].get('PRODUCT_BUNDLE_IDENTIFIER')!='tw.mars.trainmath': raise SystemExit('Unexpected target App ID')
    matches=list(re.finditer(r'(?m)^\t\t'+re.escape(cid)+r' /\*[^\n]*\*/ = \{.*?^\t\t\};',text,re.S))
    if len(matches)!=1: raise SystemExit('Unsupported project structure')
    block=matches[0].group(0)
    for key,value in settings.items():
        line='\t\t\t\t'+key+' = "'+value+'";'; pattern=r'(?m)^\t\t\t\t'+re.escape(key)+r' = [^\n]*;'
        block=re.sub(pattern,lambda _:line,block) if re.search(pattern,block) else block.replace('buildSettings = {','buildSettings = {\n'+line,1)
    text=text[:matches[0].start()]+block+text[matches[0].end():]
path.write_text(text)
PY
  clean_tool xcodebuild -project "$PROJECT" -scheme App -configuration Release -destination 'generic/platform=iOS' -archivePath "$TASK_TMP/Signed.xcarchive" -derivedDataPath "$TASK_TMP/derived" OTHER_CODE_SIGN_FLAGS="--keychain $KEYCHAIN" archive >"$TASK_TMP/archive.log" 2>&1 || fail 'explicit signed re-archive failed'
  ARCHIVE="$TASK_TMP/Signed.xcarchive"
  check_resources "$ARCHIVE/Products/Applications/App.app"
fi
python3 - "$TASK_TMP/ExportOptions.plist" "$TASK_TMP/profile.plist" "$CERT_SHA" <<'PY'
import os,plistlib,sys
profile=plistlib.load(open(sys.argv[2],'rb'))
options={'method':'app-store-connect','destination':'export','signingStyle':'manual','teamID':os.environ['APPLE_TEAM_ID'],'signingCertificate':sys.argv[3],'provisioningProfiles':{'tw.mars.trainmath':profile['UUID']},'manageAppVersionAndBuildNumber':False,'testFlightInternalTestingOnly':False,'uploadSymbols':False,'stripSwiftSymbols':True,'thinning':'<none>'}
plistlib.dump(options,open(sys.argv[1],'wb'))
PY
clean_tool xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportPath "$TASK_TMP/export" -exportOptionsPlist "$TASK_TMP/ExportOptions.plist" >"$TASK_TMP/export.log" 2>&1 || fail 'existing archive export rejected; select signed-rearchive explicitly if Xcode requires a signed archive'
ipas=("$TASK_TMP/export/"*.ipa)
[ "${#ipas[@]}" -eq 1 ] && [ -f "${ipas[0]}" ] || fail 'expected one exported IPA'
verify_ipa "${ipas[0]}"
cp "${ipas[0]}" "$OUT/TrainMath.ipa"
python3 - "$OUT" "$ROOT/output/ios-store-provenance.json" "$SOURCE/bundle-manifest.json" "$STRATEGY" <<'PY'
import hashlib,json,pathlib,sys
out=pathlib.Path(sys.argv[1]); source=json.loads(pathlib.Path(sys.argv[2]).read_text()); manifest=json.loads(pathlib.Path(sys.argv[3]).read_text())
report={'bundleId':'tw.mars.trainmath','marketingVersion':'1.0.0','buildNumber':'1','sourceRun':source['sourceRun'],'sourceSha':source['sourceSha'],'strategy':sys.argv[4],'exportMethod':'app-store-connect','signatureVerified':True,'profileVerified':True,'entitlementsVerified':True,'privacyVerified':True,'bundledResourceCount':len(manifest['files']),'bundledResourcesVerified':True,'ipaSha256':hashlib.sha256((out/'TrainMath.ipa').read_bytes()).hexdigest(),'appleUploaded':False,'appStoreApproved':False}
(out/'verification.json').write_text(json.dumps(report,indent=2))
PY
printf 'IPA exported and verified. No Apple upload was performed.\n'
