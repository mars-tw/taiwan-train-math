param(
  [Parameter(Mandatory=$true)][string]$KeyStoreFile,
  [Parameter(Mandatory=$true)][string]$KeyAlias,
  [Parameter(Mandatory=$true)][string]$BuildToolsDirectory,
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
$signApk = Join-Path $signOutput 'train-math-1.0.0.apk'
$signBundle = Join-Path $signOutput 'train-math-1.0.0.aab'
$signInputApk = Join-Path $signProjectRoot 'android/app/build/outputs/apk/release/app-release-unsigned.apk'
$signInputBundle = Join-Path $signProjectRoot 'android/app/build/outputs/bundle/release/app-release.aab'
if (!(Test-Path -LiteralPath $signInputApk) -or !(Test-Path -LiteralPath $signInputBundle)) { throw 'Run assembleRelease and bundleRelease before signing.' }
$signSdk = Join-Path $BuildToolsDirectory 'apksigner.bat'
$signJar = Join-Path $env:JAVA_HOME 'bin/jarsigner.exe'
& $signSdk sign --ks $signKeyStore --ks-key-alias $KeyAlias --ks-pass env:TRAIN_MATH_STORE_PASSWORD --key-pass env:TRAIN_MATH_KEY_PASSWORD --out $signApk $signInputApk
if ($LASTEXITCODE -ne 0) { throw 'APK signing failed.' }
& $signSdk verify --verbose --print-certs $signApk
if ($LASTEXITCODE -ne 0) { throw 'APK signature verification failed.' }
Copy-Item -LiteralPath $signInputBundle -Destination $signBundle
& $signJar -keystore $signKeyStore -storepass:env TRAIN_MATH_STORE_PASSWORD -keypass:env TRAIN_MATH_KEY_PASSWORD -sigalg SHA256withRSA -digestalg SHA-256 $signBundle $KeyAlias
if ($LASTEXITCODE -ne 0) { throw 'AAB signing failed.' }
& $signJar -verify $signBundle
if ($LASTEXITCODE -ne 0) { throw 'AAB signature verification failed.' }
$signArtifacts = foreach ($signFile in @($signApk, $signBundle)) {
  $signInfo = Get-Item -LiteralPath $signFile
  [pscustomobject]@{ name=$signInfo.Name; bytes=$signInfo.Length; sha256=(Get-FileHash -LiteralPath $signFile -Algorithm SHA256).Hash.ToLowerInvariant() }
}
[pscustomobject]@{ appId='tw.mars.trainmath'; version='1.0.0'; build=1; signed=$true; signingKeyOutsideRepository=$true; artifacts=$signArtifacts } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $signOutput 'signed-artifacts.json') -Encoding utf8
