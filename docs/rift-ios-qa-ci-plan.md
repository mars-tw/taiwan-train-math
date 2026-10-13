# Rift Forge 3D iOS device QA build, not a store submission

This manual workflow builds an iPhone/iPad device IPA from Rift Forge source commit
`a85310033f3d035b12b0721582f1e85aa56767ad` without changing
`native/build-config.json`. The release gate stays `readyForStore: false`. The IPA
is for physical QA; the workflow never calls App Store Connect.

## Frozen input

The Unity 6000.5.4f1 Windows Editor successfully exported a Development Xcode
project from a fresh detached worktree. Unity auto-serialized seven tracked
settings files, including `EditorBuildSettings.asset`, during import, so the generated Xcode
project is a recorded transformation of the clean commit, not a byte-clean
checkout. In the generated `Info.plist` only, QA preparation changed the
display/name to `Rift Forge 3D` and the build number from `0` to `1`; the
gameplay source did not change. The raw export and transform receipt remain in
`C:\MarsNativeWork\RiftReleasePrep-a853100`.

The draft GitHub Release tag `rift-ios-qa-a853100-20261013` must contain exactly
these three locally frozen inputs before dispatch:

| Asset | SHA-256 |
| --- | --- |
| `RiftForge-iOS-qa-build1-source-a853100.zip` | `a0b19a40c84a4caf0f652a6cf3cb4fa632a8598becbe1f04e78a3c29ffe3bdc3` |
| `rift-ios-qa-build1-source-manifest-a853100.json` | `70501a00e369fd784942739fbc774270b63ba33796a1b2485a46241b3b27e3ae` |
| `rift-ios-qa-brand-transform-20261013.json` | `d23b0152e8aa7075d9ddd1ea1721e74ee6f489c835e741ffdba1c1846a9337f9` |

`scripts/rift_ios_qa_verify.py source` rejects any other hashes and checks all
3,304 ZIP members, the generated app ID, `Info.plist`, and playable scene.
This full extraction/verification passed locally. The ZIP is 305,545,928 bytes.
The raw unsigned export ZIP, which is not sent to CI, is separately preserved
with SHA-256 `77a2d2636cf5ffc21b2b124c9a0383c348eb1f38758dd70b6ddfb004a89671a3`.

## Runner and secrets

Run `.github/workflows/rift-ios-qa.yml` manually on `main` only after its code
is independently reviewed and merged. It requires the existing free
`macos-15` runner with Xcode 26.3 and a dedicated GitHub environment named
`game-store-rift-forge-3d`. Configure four environment secrets there:
`APPLE_DISTRIBUTION_P12_BASE64`, `APPLE_DISTRIBUTION_P12_PASSWORD`,
`APPLE_APPSTORE_PROFILE_BASE64`, and `APPLE_TEAM_ID`. Reuse only the verified
shared Apple Distribution identity; the profile must be Rift's own App Store
profile. No secret value enters the source Release, repository, or run summary.

The local Rift profile was read and verified: UUID
`6b58b899-07eb-49bb-ba17-19f80ea11eaa`, SHA-256
`b6eab8c786950d77f64b842b87050381cca26d4a0b79c53f0619f0d262d08c52`,
Team `93L76Q5PT8`, entitlement
`93L76Q5PT8.tw.mars.riftforge3d`, `get-task-allow=false`, no device list,
expiry 2027-10-06. The signer repeats these checks on the Mac runner and
requires the imported P12's certificate SHA-1 to match the profile.

## CI sequence

1. Download the three assets from the fixed draft Release; verify the release
   is still a draft and hash/extract every Xcode project file before exposing
   signing secrets.
2. Attempt an unsigned iOS Simulator compile as a diagnostic. The source is
   device-targeted; a simulator failure is recorded, not called a pass and not
   treated as proof that device compilation failed.
3. Recheck source hashes. Only then import the Rift profile and shared P12
   into a temporary keychain, archive for generic iOS device and export a
   signed QA IPA. The temporary signing files and profile are cleaned up.
4. Verify `tw.mars.riftforge3d`, version `1.0.0` build `1`, arm64,
   `Rift Forge 3D`, Apple code signature, Team/profile/certificate match,
   entitlements, and that physical-device/store flags remain false.
5. Package the exact-run IPA and receipts into a unique ZIP, attach it to the
   same **draft** Release once, and read back its size and SHA-256. If an upload
   fails or its outcome is unclear, inspect that run's asset before retrying.

The current `all-games-ios.yml` and Farm workflows are pinned to other games
and cannot build this Unity Xcode project. The Rift workflow therefore adds a
new, isolated path without changing those workflows. The draft Release and
Rift-specific environment have not been created yet; no CI run has occurred.

## QA before any store build

The isolated Android Development APK physically reached the final Warden
victory on Pixel 8 Pro/Android 17, but it is **not** the canonical APK byte
identity. Canonical source `a853100` produced a distinct debug APK with SHA-256
`3cb4b081a343a65f82521ddaf40a0a57624b1c1377d5748b7d424a48f1f8daf2`.
Run that exact canonical APK through four waves, forge, input/multitouch,
pause/background, safe area, crash and performance checks. Once the iOS QA IPA
exists, run its exact bytes on a physical current-iOS iPhone and iPad. Only
then consider platform-specific release readiness evidence and a signed
non-Development AAB/IPA. The current gate requires `schemaVersion: 1`,
`sourceStage: complete-game`, `readyForStore: true`, and the real Main scene;
it has no evidence-hash or per-platform readiness fields.

App icons, accepted gameplay screenshots, support/privacy URLs, and final
data-collection declarations remain open. No store app record exists for Rift.
