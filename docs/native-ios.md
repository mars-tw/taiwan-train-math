# 小小列車長：iOS 建置、簽署與 TestFlight

官方查核日期：2026-10-06。此文件提供操作路徑，尚無本遊戲的已簽署 IPA、TestFlight 上傳或實體 iPhone／iPad 驗收證據。

原生 App 版本為 **1.0.0／build 1**，Web 為 **1.11.0**。本地沒有實體 Mac，`macos-26` 雲端編譯仍在準備，尚無本遊戲的成功 iOS 編譯記錄；Android 首輪 APK 成功不代表 iOS 已成功。

## 工具與平台紀錄

Capacitor 8 要 Node.js 22+、macOS 上的 Xcode 26+ 與 Command Line Tools，SPM 為預設依賴方式。[Capacitor 環境](https://capacitorjs.com/docs/getting-started/environment-setup)

Apple 上傳下限為 Xcode 26+／iOS 26 SDK。Xcode 26／26.3 可在 macOS Sequoia 15.6+ 執行；Xcode 27 的表列下限為 macOS Tahoe 26.6。雲端 runner 和實體 Mac 都應先記錄實際 `xcodebuild -version`／SDK，不只看 runner 名稱。[Apple 上傳要求](https://developer.apple.com/news/upcoming-requirements/)、[工具版本表](https://developer.apple.com/xcode/system-requirements)

本遊戲原生工程的 Deployment Target 已設為 15.4，對應 `Object.hasOwn`、`Array.at`、`dialog` 的 WebKit 支援下限；最低 OS 仍需實機驗證。[WebKit 15.4](https://webkit.org/blog/12445/new-webkit-features-in-safari-15-4/)

| 欄位 | 本遊戲狀態 |
| --- | --- |
| 展示名稱 | 小小列車長 |
| Bundle Identifier | `tw.mars.trainmath` 草案，平台登記待確認 |
| Version／Build | 1.0.0／1；Web 1.11.0 為獨立版本 |
| Apple membership | 使用者已確認啟用 |
| Team ID／Apple Seller／App Store Connect App 記錄 | 未設定／未確認 |
| 簽署憑證、私鑰、Provisioning Profile | 本遊戲仍待确认；另一遊戲的私鑰授權僅限該遊戲，不共用或複製到本 App |
| Review／TestFlight 聯絡信箱 | a820628a@gmail.com |
| Review 聯絡姓名／電話 | 未設定 |
| 支援 URL | https://mars-tw.github.io/taiwan-train-math/support.html，來源就緒，部署待確認 |
| 隱私 URL | https://mars-tw.github.io/taiwan-train-math/privacy.html，來源就緒，部署待確認 |

## 先建立 unsigned 可驗證產物

在 repo 的實際 Capacitor 專案目錄使用 lockfile；有現成 `ios/` 時不要重新 `cap add ios`。先完成 web assets 本地打包與素材驗證，再同步。以下以 `ios/App/App.xcodeproj` 的 SPM 專案示範；若本專案採 CocoaPods，改用實際 workspace，勿混用兩種依賴入口。

```sh
npm ci
npm run native:build
npx cap sync ios
node scripts/configure-native-projects.mjs
xcodebuild -version
xcrun --sdk iphoneos --show-sdk-version
xcodebuild -project ios/App/App.xcodeproj -scheme App \
  -configuration Debug -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath output/ios-derived CODE_SIGNING_ALLOWED=NO build
xcodebuild -project ios/App/App.xcodeproj -scheme App \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath output/TrainMath-unsigned.xcarchive \
  CODE_SIGNING_ALLOWED=NO archive
```

Windows 不能本機執行 Xcode，但可由本 repo 的 `macos-26` GitHub Actions runner 執行上述建置。目前仍是準備狀態；建置成功後才會產生 simulator `.app` 與 unsigned `.xcarchive`，兩者不是已簽署 IPA，不能當作實體手機安裝包或 TestFlight 已完成。CI 記錄 commit、工具版本、素材清單、archive 路徑及 hash；不把私鑰放公開 artifact。[GitHub runner](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

簽署與上傳也可由具備本遊戲授權設定的 macOS CI 執行，不必推定使用者一定要先購買實體 Mac；目前尚未配置本遊戲的簽署流程。本文件保留 Xcode 手動路徑供實際持有工具與權限的人操作，實體 iPhone／iPad 驗收仍需另做。

確認 App.app 內有全部本地資源、照片授權及 `PrivacyInfo.xcprivacy`；以 `plutil -lint` 驗 manifest。使用 Preferences 的 UserDefaults reason 須與實際儲存用途一致，不能只因表單要求而填碼。[Preferences Privacy Manifest](https://capacitorjs.com/docs/apis/preferences)

## Mac 上的簽署與實機

1. 取得本遊戲最新 commit，按 repo lockfile 執行 `npm ci`、`npm run native:build`，再執行 `npx cap sync ios`、`node scripts/configure-native-projects.mjs`、`npx cap open ios`；不要依賴另一遊戲的 native 資料夾。設定檔應為本遊戲的 `appId=tw.mars.trainmath`、`appName=小小列車長`、`webDir=dist-native`，Version／Build 為 1.0.0／1，Release 不得有遠端 `server.url`。
2. 在 Xcode 的 Settings → Accounts 加入已有會員資格的本人 Apple 帳戶，使用正常登入；在 App target 的 Signing & Capabilities 選核准 Team，確認 Bundle ID、Display Name、Version、Build Number 與最低 iOS。
3. 若採 Automatically manage signing，由 Xcode 配置該 Team／本 Bundle ID 的設定；帳戶權限不足或 App ID 未登記時保持待辦。不要冒用 Personal Team 當成可供 TestFlight 的正式資格。
4. 選實體 iPhone／iPad Run，完成要求的裝置信任／Developer Mode。飛航模式下首次開啟，測 20 種玩法、照片、離開 App 連結的成人乘法關卡、取消、靜音／本機語音、旋轉與大字模式。乘法關卡不是身分驗證或法律同意。
5. 操作一半時切背景、鎖屏與結束 App；確認停止聲音／計時器、保存已實作部分，重開不換題。完成旅程後重開不能再領一次獎勵。
6. 測清除紀錄及一次更新；清除要涵蓋 native 儲存，更新不得誤清護照。不宣稱重新安裝必定恢復紀錄，系統備份與解除安裝行為依實際設定說明。

## Archive、Validate 與上傳

以下是後續獲授權的操作，這一輪沒有執行上傳。

1. 在 Xcode 選 App scheme、Release、`Any iOS Device`／generic iOS device，而非 simulator，按 Product → Archive。
2. Organizer 檢查本遊戲 Bundle ID、Team、Version／Build、簽署狀態與 Privacy Report。新上傳的 Build Number 需可識別，不覆用已上傳 build。
3. 按 Validate App，解決簽署、資源、icon、Privacy Manifest、SDK 及架構錯誤；Validate 成功不等於 App Review 通過。
4. 只有在本遊戲 App Store Connect 記錄、metadata 與聯絡人齊備，且已獲本次上傳授權時，選 Distribute App → App Store Connect → Upload。保留本遊戲的處理結果及 build 記錄。[Apple Upload builds](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)
5. 在 App Store Connect 選該 build，依實際加密／隱私行為回答 export compliance。不要僅因是 WebView 就自動勾「沒有加密」，也不要用其他遊戲的審查資訊。

## TestFlight 與正式審查

先建立內部測試群組，指定本遊戲 build；內部測試與正式上架不同。需要外部親子試玩時，新增外部群組、What to Test、公開客服信箱及 Review 聯絡資料，依要求提交 TestFlight App Review，核准後才邀請測試者。[內部測試](https://developer.apple.com/help/app-store-connect/test-a-beta-version/add-internal-testers/)、[外部測試](https://developer.apple.com/help/app-store-connect/test-a-beta-version/invite-external-testers/)

優先測最低支援 iOS、目前 iOS、iPhone／iPad、飛航首次啟動及語音不可用的裝置；收集匿名操作問題即可，不在兒童 App 內加入分析 SDK。不要把 simulator 截圖或 unsigned archive 標為實機成果。

正式送審用 repo 的 `store-listing/zh-TW/review-notes.md`；以原生 1.0.0／build 1 核對截圖與 App Privacy，再確認公開支援／隱私 URL 可讀，補 Kids 分組及聯絡姓名／電話。未完成欄位在送出前解決，不用 Web 1.11.0 取代原生版本。
