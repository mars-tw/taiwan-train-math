#!/usr/bin/env bash
# Compile and sign the pinned Rift Forge Development Xcode export for device QA.
# No App Store Connect upload, review submission, or release gate change.
set -euo pipefail

die() { echo "Rift iOS QA signing failed: $*" >&2; exit 1; }
[[ "$(uname -s)" == Darwin ]] || die 'macOS and Xcode are required'
for command in python3 security xcodebuild codesign ditto lipo; do
  command -v "$command" >/dev/null || die "Required tool missing: $command"
done
: "${RIFT_PROJECT_DIR:?Set RIFT_PROJECT_DIR to the verified Xcode source directory}"
: "${RIFT_OUTPUT_DIR:?Set RIFT_OUTPUT_DIR to a fresh QA output directory}"
: "${RIFT_VERIFY_SCRIPT:?Set RIFT_VERIFY_SCRIPT to the trusted verifier}"
: "${APPLE_DISTRIBUTION_P12_BASE64:?Missing Apple Distribution P12 secret}"
: "${APPLE_DISTRIBUTION_P12_PASSWORD:?Missing P12 password secret}"
: "${APPLE_APPSTORE_PROFILE_BASE64:?Missing Rift-specific App Store profile secret}"
: "${APPLE_TEAM_ID:?Missing Apple Team ID secret}"
[[ "$APPLE_TEAM_ID" == '93L76Q5PT8' ]] || die 'Apple Team differs from Rift profile'
[[ -f "$RIFT_PROJECT_DIR/Unity-iPhone.xcodeproj/project.pbxproj" ]] || die 'Unity Xcode project missing'
[[ -f "$RIFT_PROJECT_DIR/Info.plist" ]] || die 'Unity Info.plist missing'
[[ -f "$RIFT_VERIFY_SCRIPT" ]] || die 'Trusted verifier missing'
[[ ! -e "$RIFT_OUTPUT_DIR" ]] || die 'QA output directory must be fresh'
mkdir -p "$RIFT_OUTPUT_DIR"

work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/rift-ios-qa.XXXXXXXX")"
keychain="$work/rift-qa.keychain-db"
profile_installed=''
keychain_created=0
old_keychains=()
while IFS= read -r line; do
  [[ -n "$line" ]] && old_keychains+=("$line")
done < <(security list-keychains -d user | sed 's/^[[:space:]]*"//;s/"$//')
cleanup() {
  set +e
  if [[ ${#old_keychains[@]} -gt 0 ]]; then security list-keychains -d user -s "${old_keychains[@]}" >/dev/null 2>&1; fi
  if [[ -n "$profile_installed" ]]; then rm -f -- "$profile_installed"; fi
  if [[ "$keychain_created" == 1 ]]; then security delete-keychain "$keychain" >/dev/null 2>&1; fi
  rm -f -- "$work/distribution.p12" "$work/rift.mobileprovision" "$work/profile.plist" "$work/ExportOptions.plist" "$work/profile-proof.json"
}
trap cleanup EXIT

RIFT_WORK="$work" python3 - <<'PY'
import base64,os,pathlib
root=pathlib.Path(os.environ['RIFT_WORK'])
for env,name in [('APPLE_DISTRIBUTION_P12_BASE64','distribution.p12'),
                 ('APPLE_APPSTORE_PROFILE_BASE64','rift.mobileprovision')]:
    try: value=base64.b64decode(os.environ[env],validate=True)
    except ValueError: raise SystemExit('Signing secret is not valid base64')
    if not value: raise SystemExit('Empty signing secret')
    path=root/name
    with path.open('xb') as out: out.write(value)
    path.chmod(0o600)
PY
security cms -D -i "$work/rift.mobileprovision" -o "$work/profile.plist" >/dev/null 2>&1 || die 'Rift profile CMS decode failed'
RIFT_WORK="$work" python3 - <<'PY'
import datetime,hashlib,json,os,pathlib,plistlib
root=pathlib.Path(os.environ['RIFT_WORK'])
raw=(root/'rift.mobileprovision').read_bytes()
profile=plistlib.loads((root/'profile.plist').read_bytes())
ent=profile.get('Entitlements',{})
certs=profile.get('DeveloperCertificates')
if (hashlib.sha256(raw).hexdigest()!='b6eab8c786950d77f64b842b87050381cca26d4a0b79c53f0619f0d262d08c52'
    or profile.get('TeamIdentifier')!=['93L76Q5PT8']
    or ent.get('application-identifier')!='93L76Q5PT8.tw.mars.riftforge3d'
    or ent.get('get-task-allow') is not False
    or bool(profile.get('ProvisionedDevices'))
    or profile.get('ExpirationDate')<=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    or not isinstance(certs,list) or len(certs)!=1):
    raise SystemExit('Rift App Store profile does not match pinned app/team/distribution requirements')
proof={'uuid':profile['UUID'],'certificateSha1':hashlib.sha1(certs[0]).hexdigest(),
       'teamId':'93L76Q5PT8','appId':'tw.mars.riftforge3d','profileSha256':hashlib.sha256(raw).hexdigest()}
(root/'profile-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
PY

keychain_password="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
security create-keychain -p "$keychain_password" "$keychain" >/dev/null
keychain_created=1
security unlock-keychain -p "$keychain_password" "$keychain" >/dev/null
security set-keychain-settings -lut 21600 "$keychain" >/dev/null
security import "$work/distribution.p12" -k "$keychain" -P "$APPLE_DISTRIBUTION_P12_PASSWORD" -T /usr/bin/codesign -T /usr/bin/security >/dev/null
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$keychain_password" "$keychain" >/dev/null
security list-keychains -d user -s "$keychain" "${old_keychains[@]}" >/dev/null
profile_uuid="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["uuid"])' "$work/profile-proof.json")"
certificate_sha1="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["certificateSha1"])' "$work/profile-proof.json")"
security find-identity -v -p codesigning "$keychain" | tr '[:upper:]' '[:lower:]' | grep -q "$certificate_sha1" || die 'Imported P12 does not match Rift profile certificate'
profile_dir="$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"
mkdir -p "$profile_dir"
profile_path="$profile_dir/$profile_uuid.mobileprovision"
[[ ! -e "$profile_path" ]] || die 'Refusing to overwrite a pre-existing profile'
PROFILE_SOURCE="$work/rift.mobileprovision" PROFILE_DEST="$profile_path" python3 - <<'PY'
import os,pathlib
source=pathlib.Path(os.environ['PROFILE_SOURCE'])
destination=pathlib.Path(os.environ['PROFILE_DEST'])
created=False
try:
    with destination.open('xb') as output:
        created=True
        output.write(source.read_bytes())
    destination.chmod(0o600)
except Exception:
    # Remove only the file this process managed to create, never a prior profile.
    if created: destination.unlink(missing_ok=True)
    raise
PY
profile_installed="$profile_path"

RIFT_WORK="$work" python3 - <<'PY'
import json,os,pathlib,plistlib
root=pathlib.Path(os.environ['RIFT_WORK'])
proof=json.loads((root/'profile-proof.json').read_text())
options={'method':'app-store-connect','destination':'export','signingStyle':'manual',
         'teamID':proof['teamId'],'signingCertificate':proof['certificateSha1'],
         'provisioningProfiles':{proof['appId']:proof['uuid']},
         'manageAppVersionAndBuildNumber':False,'uploadSymbols':False,
         'testFlightInternalTestingOnly':False}
(root/'ExportOptions.plist').write_bytes(plistlib.dumps(options))
PY
unset APPLE_DISTRIBUTION_P12_BASE64 APPLE_DISTRIBUTION_P12_PASSWORD APPLE_APPSTORE_PROFILE_BASE64

project="$RIFT_PROJECT_DIR/Unity-iPhone.xcodeproj"
archive="$work/RiftForgeQA.xcarchive"
derived="$work/derived"
(
  cd "$RIFT_PROJECT_DIR"
  xcodebuild -project "$project" -scheme Unity-iPhone -configuration Release \
    -sdk iphoneos -destination 'generic/platform=iOS' -archivePath "$archive" \
    -derivedDataPath "$derived" \
    "DEVELOPMENT_TEAM=$APPLE_TEAM_ID" "CODE_SIGN_STYLE=Manual" \
    "CODE_SIGN_IDENTITY=$certificate_sha1" \
    "PROVISIONING_PROFILE_APP=$profile_uuid" \
    "PROVISIONING_PROFILE_SPECIFIER_APP=$profile_uuid" \
    'CURRENT_PROJECT_VERSION=1' 'MARKETING_VERSION=1.0.0' \
    "OTHER_CODE_SIGN_FLAGS=--keychain $keychain" archive >"$RIFT_OUTPUT_DIR/archive.log" 2>&1
) || die 'Xcode device archive failed; inspect archive.log (no retry or store upload)'
[[ -d "$archive/Products/Applications" ]] || die 'Signed device archive has no application'
xcodebuild -exportArchive -archivePath "$archive" -exportPath "$work/export" \
  -exportOptionsPlist "$work/ExportOptions.plist" >"$RIFT_OUTPUT_DIR/export.log" 2>&1 \
  || die 'Xcode IPA export failed; inspect export.log (no retry or store upload)'
shopt -s nullglob
ipas=("$work/export/"*.ipa)
[[ ${#ipas[@]} -eq 1 ]] || die 'Expected exactly one exported IPA'
cp "${ipas[0]}" "$RIFT_OUTPUT_DIR/signed-qa.ipa"
python3 "$RIFT_VERIFY_SCRIPT" ipa --ipa "$RIFT_OUTPUT_DIR/signed-qa.ipa" \
  --receipt "$RIFT_OUTPUT_DIR/ipa-structure-verification.json"
ditto -x -k "$RIFT_OUTPUT_DIR/signed-qa.ipa" "$work/unpacked"
apps=("$work/unpacked/Payload/"*.app)
[[ ${#apps[@]} -eq 1 ]] || die 'Expected exactly one extracted app'
app="${apps[0]}"
codesign --verify --deep --strict --verbose=2 "$app" >"$RIFT_OUTPUT_DIR/codesign-verify.log" 2>&1 \
  || die 'Apple code signature verification failed'
framework="$app/Frameworks/UnityFramework.framework"
[[ -d "$framework" ]] || die 'UnityFramework missing from signed app'
codesign --verify --strict -R='anchor apple generic' "$app" >>"$RIFT_OUTPUT_DIR/codesign-verify.log" 2>&1 \
  || die 'Signed app is not Apple-anchored'
codesign --verify --strict -R='anchor apple generic' "$framework" >>"$RIFT_OUTPUT_DIR/codesign-verify.log" 2>&1 \
  || die 'Signed UnityFramework is not Apple-anchored'
codesign -d --entitlements :- "$app" >"$work/signed-entitlements.plist" 2>/dev/null \
  || die 'Signed app entitlements unavailable'
codesign -d --extract-certificates="$work/cert" "$app" >/dev/null 2>&1 \
  || die 'Signed app certificate unavailable'
RIFT_WORK="$work" RIFT_OUTPUT_DIR="$RIFT_OUTPUT_DIR" python3 - <<'PY'
import hashlib,json,os,pathlib,plistlib,subprocess
work=pathlib.Path(os.environ['RIFT_WORK'])
out=pathlib.Path(os.environ['RIFT_OUTPUT_DIR'])
proof=json.loads((work/'profile-proof.json').read_text())
ent=plistlib.loads((work/'signed-entitlements.plist').read_bytes())
cert=(work/'cert0').read_bytes()
if (ent.get('application-identifier')!='93L76Q5PT8.tw.mars.riftforge3d'
    or ent.get('get-task-allow') is not False
    or hashlib.sha1(cert).hexdigest()!=proof['certificateSha1']):
    raise SystemExit('Signed app entitlements or certificate differ from Rift profile')
app=next((work/'unpacked/Payload').glob('*.app'))
info=plistlib.loads((app/'Info.plist').read_bytes())
exe=app/info['CFBundleExecutable']
archs=subprocess.check_output(['lipo','-archs',str(exe)],text=True).split()
framework=app/'Frameworks/UnityFramework.framework/UnityFramework'
framework_archs=subprocess.check_output(['lipo','-archs',str(framework)],text=True).split()
if 'arm64' not in archs or 'arm64' not in framework_archs:
    raise SystemExit('Signed app or UnityFramework lacks arm64 device architecture')
ipa=out/'signed-qa.ipa'
report={'status':'SIGNED_QA_IPA_VERIFIED','appId':'tw.mars.riftforge3d',
        'version':'1.0.0','build':1,'sourceCommit':'a85310033f3d035b12b0721582f1e85aa56767ad',
        'sourceZipSha256':'a0b19a40c84a4caf0f652a6cf3cb4fa632a8598becbe1f04e78a3c29ffe3bdc3',
        'ipaSha256':hashlib.sha256(ipa.read_bytes()).hexdigest(),'ipaBytes':ipa.stat().st_size,
        'profileUuid':proof['uuid'],'profileCertificateSha1':proof['certificateSha1'],
        'codesignVerified':True,'entitlementsVerified':True,'arm64Verified':True,
        'physicalDeviceTested':False,'storeUploaded':False,'storeReady':False}
(out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
PY
echo 'Rift Forge signed iOS QA IPA verified. No store upload or release readiness claim.'
