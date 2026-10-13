param(
  [Parameter(Mandatory=$true)][string]$KeyStoreFile,
  [Parameter(Mandatory=$true)][string]$KeyAlias,
  [Parameter(Mandatory=$true)][string]$BuildToolsDirectory,
  [string]$BundleToolJar = (Join-Path $env:USERPROFILE '.codex/tools/island-transport-native/bundletool-all-1.18.3.jar'),
  [string]$ArtifactDirectory = 'release/android'
)
$ErrorActionPreference = 'Stop'
# Supply passwords as process environment values. Never place them in source,
# command arguments, build logs, or the public release directory.
if (!$env:TRAIN_MATH_STORE_PASSWORD -or !$env:TRAIN_MATH_KEY_PASSWORD) { throw 'Signing password environment values are required.' }
if (!$env:JAVA_HOME) { throw 'JAVA_HOME must point to JDK 21 or later.' }
$signProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$signOutput = [IO.Path]::GetFullPath((Join-Path $signProjectRoot $ArtifactDirectory))
if (!$signOutput.StartsWith($signProjectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Signing output must stay inside this project.' }
$signKeyStore = (Resolve-Path -LiteralPath $KeyStoreFile).Path
if ($signKeyStore.StartsWith($signProjectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Keep the private signing keystore outside the repository.' }
New-Item -ItemType Directory -Force -Path $signOutput | Out-Null
$signApk = Join-Path $signOutput 'train-math-1.0.0-b2.apk'
$signBundle = Join-Path $signOutput 'train-math-1.0.0-b2.aab'
$signReceipt = Join-Path $signOutput 'signed-artifacts.json'
$signVerifyReceipt = Join-Path $signOutput 'android-verification.json'
if ((Test-Path -LiteralPath $signApk) -or (Test-Path -LiteralPath $signBundle) -or (Test-Path -LiteralPath $signReceipt) -or (Test-Path -LiteralPath $signVerifyReceipt)) { throw 'Refusing to replace an existing signed build 2 output.' }
$signInputApk = Join-Path $signProjectRoot 'android/app/build/outputs/apk/release/app-release-unsigned.apk'
$signInputBundle = Join-Path $signProjectRoot 'android/app/build/outputs/bundle/release/app-release.aab'
$signManifest = Join-Path $signProjectRoot 'output/native/bundle-manifest.json'
if (!(Test-Path -LiteralPath $signInputApk) -or !(Test-Path -LiteralPath $signInputBundle)) { throw 'Run assembleRelease and bundleRelease before signing.' }
# Rebuild the current source manifest without exposing signing passwords to npm.
# The later ZIP checks then reject packages built from older source bytes.
$signStorePassword = $env:TRAIN_MATH_STORE_PASSWORD
$signKeyPassword = $env:TRAIN_MATH_KEY_PASSWORD
try {
  Remove-Item -Path Env:TRAIN_MATH_STORE_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item -Path Env:TRAIN_MATH_KEY_PASSWORD -ErrorAction SilentlyContinue
  Push-Location -LiteralPath $signProjectRoot
  try {
    & npm.cmd run native:build
    if ($LASTEXITCODE -ne 0) { throw 'Current source bundle build failed.' }
  } finally { Pop-Location }
} finally {
  $env:TRAIN_MATH_STORE_PASSWORD = $signStorePassword
  $env:TRAIN_MATH_KEY_PASSWORD = $signKeyPassword
}
if (!(Test-Path -LiteralPath $signManifest)) { throw 'Run native:build before signing.' }
$signSdk = Join-Path $BuildToolsDirectory 'apksigner.bat'
$signAapt = Join-Path $BuildToolsDirectory 'aapt.exe'
$signJava = Join-Path $env:JAVA_HOME 'bin/java.exe'
$signJar = Join-Path $env:JAVA_HOME 'bin/jarsigner.exe'
if (!(Test-Path -LiteralPath $signAapt) -or !(Test-Path -LiteralPath $signJava) -or !(Test-Path -LiteralPath $BundleToolJar)) { throw 'Android aapt, Java, and pinned bundletool are required.' }
if ((Get-FileHash -LiteralPath $BundleToolJar -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29') { throw 'Bundletool digest differs from reviewed 1.18.3.' }
$signPython = (Get-Command python -ErrorAction Stop).Source
& $signSdk sign --ks $signKeyStore --ks-key-alias $KeyAlias --ks-pass env:TRAIN_MATH_STORE_PASSWORD --key-pass env:TRAIN_MATH_KEY_PASSWORD --out $signApk $signInputApk
if ($LASTEXITCODE -ne 0) { throw 'APK signing failed.' }
& $signSdk verify --verbose --print-certs $signApk
if ($LASTEXITCODE -ne 0) { throw 'APK signature verification failed.' }
$signBadging = & $signAapt dump badging $signApk
if ($LASTEXITCODE -ne 0 -or !($signBadging | Select-String -SimpleMatch "package: name='tw.mars.trainmath' versionCode='2' versionName='1.0.0'")) { throw 'Signed APK identity/version/build verification failed.' }
Copy-Item -LiteralPath $signInputBundle -Destination $signBundle
& $signJar -keystore $signKeyStore -storepass:env TRAIN_MATH_STORE_PASSWORD -keypass:env TRAIN_MATH_KEY_PASSWORD -sigalg SHA256withRSA -digestalg SHA-256 $signBundle $KeyAlias
if ($LASTEXITCODE -ne 0) { throw 'AAB signing failed.' }
& $signJar -verify $signBundle
if ($LASTEXITCODE -ne 0) { throw 'AAB signature verification failed.' }
& $signPython (Join-Path $PSScriptRoot 'verify-android-signed.py') --apk $signApk --aab $signBundle --manifest $signManifest --aapt $signAapt --java $signJava --bundletool $BundleToolJar --receipt $signVerifyReceipt
if ($LASTEXITCODE -ne 0) { throw 'Signed APK/AAB identity or source equivalence verification failed.' }
$signProof = Get-Content -LiteralPath $signVerifyReceipt -Raw | ConvertFrom-Json
if ($signProof.signedApkAndAabSourceEquivalent -ne $true -or $signProof.payloadFilesVerifiedInBoth -lt 1) { throw 'Signed package verification receipt is incomplete.' }
$signArtifacts = foreach ($signFile in @($signApk, $signBundle)) {
  $signInfo = Get-Item -LiteralPath $signFile
  [pscustomobject]@{ name=$signInfo.Name; bytes=$signInfo.Length; sha256=(Get-FileHash -LiteralPath $signFile -Algorithm SHA256).Hash.ToLowerInvariant() }
}
[pscustomobject]@{ appId='tw.mars.trainmath'; version='1.0.0'; build=2; signed=$true; signingKeyOutsideRepository=$true; sourceManifestSha256=$signProof.sourceManifestSha256; payloadFilesVerifiedInBoth=$signProof.payloadFilesVerifiedInBoth; signedApkAndAabSourceEquivalent=$true; verificationFile='android-verification.json'; artifacts=$signArtifacts } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $signReceipt -Encoding utf8
