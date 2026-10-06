# 小小列車長：App 商店準備

查核日期：2026-10-06。這是原生包與送審資料的準備清單，未代表已簽署、已上傳、已通過審查或已完成實體裝置驗收。平台要求會更新，送件當日再核一次。

版本基準：原生 App **1.0.0／build 1**，Web **1.11.0**。Android 首輪測試 APK 已實際編譯成功，release AAB 未簽署；iOS 的 macOS 26 雲端編譯仍在準備，尚無成功建置記錄。

## 已知帳戶與待填資料

| 項目 | 狀態 |
| --- | --- |
| App 展示名稱 | 小小列車長，沿用目前網站／manifest 名稱 |
| 本遊戲獨立 Bundle ID／Android package ID | `tw.mars.trainmath`，已選定草案，尚須在本遊戲的平台紀錄確認可用 |
| Google 公開開發者名稱 | MARS_TW，使用者已確認 |
| 公開客服信箱 | a820628a@gmail.com，使用者已選擇並公開 |
| Apple Developer Program | 使用者已確認會員啟用；本遊戲 App Store Connect 紀錄、Team ID／Seller 名稱尚未確認 |
| Google Play 帳戶 | 身分已驗證；裝置／電話驗證仍待完成 |
| 支援頁 URL | https://mars-tw.github.io/taiwan-train-math/support.html，來源已完成，公開部署待確認 |
| 原生 App 隱私政策 URL | https://mars-tw.github.io/taiwan-train-math/privacy.html，來源已完成，公開部署待確認；區分 Web／原生語音與儲存行為 |
| 商店年齡問卷、Kids 分組、IARC | 未填；遊戲的 3–4／5–6／7–8 難度不是商店自動評級 |
| 原生版本／Build Number | 1.0.0／1；Android versionName／versionCode 及 iOS Version／Build 對應這組數值 |
| Web 版本 | 1.11.0，與原生 App 商店版本分開 |
| 截圖、價格／地區 | 待正式包驗收及發布者選擇 |

本遊戲不得使用其他遊戲的 Bundle ID 或 App Store 紀錄。另一遊戲的 Apple 私鑰授權僅限該遊戲，不共用到本 App；本遊戲簽署方式仍須另行確認。帳戶名稱與公開信箱可用於本稿，Apple Seller／法定權利人仍以該帳戶實際資料為準。

## 官方要求與本案做法

| 項目 | 目前要求／本案準備 |
| --- | --- |
| Capacitor 8 | Node.js 22+、Xcode 26+；iOS 建置在 macOS 執行，預設推薦 SPM。現有套件固定於 repo lockfile，不另裝全域最新版。[環境要求](https://capacitorjs.com/docs/getting-started/environment-setup) |
| Apple 上傳工具 | 2026-04-28 起，iOS／iPadOS 上傳包需以 Xcode 26+、iOS／iPadOS 26 SDK 建置；SDK 版本不等於最低可安裝的 iOS 版本。[上傳要求](https://developer.apple.com/news/upcoming-requirements/) |
| macOS | Xcode 26／26.3 的最低 macOS 為 Sequoia 15.6；官方表中的 Xcode 27 需 Tahoe 26.6+。依選用工具匹配，不要求舊 Mac 強裝最新 Xcode。[Apple 工具表](https://developer.apple.com/xcode/system-requirements) |
| 本遊戲最低 iOS | Capacitor 支援 iOS 15+，但本遊戲使用 `Object.hasOwn`、`Array.at`、`dialog.showModal`，WebKit 15.4 才加入；無相容補丁時，Deployment Target 至少 15.4，並驗最低版本實機。不得把 Capacitor 的 15.0 下限當成遊戲已驗證下限。[Capacitor iOS](https://capacitorjs.com/docs/ios)、[WebKit 15.4](https://webkit.org/blog/12445/new-webkit-features-in-safari-15-4/) |
| Google target API | 2026-08-31 起，新手機／平板 App 與更新需 target Android 16／API 36+。不以未申請的延期當成符合要求。[官方 API 要求](https://support.google.com/googleplay/android-developer/answer/11926878) |
| 兒童產品 | Apple 建議參與 Made for Kids，選符合主目標的年齡段；Google 的 3–8 歲設計對應「5 歲以下」與「6–8 歲」，成年人陪玩不等於產品面向所有年齡。[Apple Kids](https://developer.apple.com/kids/)、[Google Families](https://support.google.com/googleplay/android-developer/answer/9893335) |
| 有效遊戲功能 | 正式包應隨附 20 種遊戲、列車資料、照片與故事素材；不使用遠端 `server.url` 把網站套入 WebView。離線互動、裝置生命週期及可靠續玩是本案價值，但不保證審核通過。[Apple 4.2](https://developer.apple.com/app-store/review/guidelines/#minimum-functionality) |

## 必要的家長區域

Apple Kids 對外連結需位於家長門檻後；這也包含照片原檔、作者授權、政府來源、GitHub、客服郵件與外部隱私網站。App 內可直接閱讀本地來源署名與隱私文字，點外連才請家長操作。[Apple Kids 要求](https://developer.apple.com/kids/)

本 App 的「兒童家長關卡」攔截離開 App 的連結，要求成人計算畫面上的乘法題後才放行，並可取消返回。它不驗證身分，也不代表法律上的兒童資料蒐集同意。通過只放行本次目的，不將關卡結果寫進兒童護照；退到背景、取消或重新啟動後收回放行。[Apple 5.1.4](https://developer.apple.com/app-store/review/guidelines/#kids)

遊戲、選車、難度、故事章節與免費禮物不增加額外門檻。沒有購買功能，不增加 IAP 或廣告 SDK。清除本機紀錄維持清楚的確認與取消操作。

## 原生完成條件

- **離線包**：首次安裝即開飛航模式；全部 20 種玩法、58 張已核實車照片、59 個圖鑑條目、故事與來源署名可讀，LDK59 仍保持照片待補。外部連結不可成為過關條件。
- **語音／音效**：原生版預設不使用遠端 Web Speech；只使用已安裝且確認在本機處理的中文語音。缺語音時維持文字／靜音，不要求麥克風、錄音或語音辨識權限。背景、鎖屏、電話中斷與離開題目要停音，回前景不自動重播。參考 [Apple AVSpeechSynthesizer](https://developer.apple.com/documentation/avfaudio/avspeechsynthesizer) 與 [Capacitor App 生命週期](https://capacitorjs.com/docs/apis/app)。
- **續玩**：原生關閉／OS 回收後，恢復同一題的配方與已實際操作；不保存算術輸入、錯答文字或家長門檻。先停計時器，再存實走指令前綴；完成後先清暫存，重啟不重領獎勵。
- **持久儲存**：不用 WebView `sessionStorage` 保證 App 關閉後續玩；原生儲存須有初始化、完成寫入與失敗回饋，不能把 async Preferences 當成已同步寫成功。系統備份／清除／解除安裝的行為按實際包說明。[Capacitor Storage](https://capacitorjs.com/docs/guides/storage)
- **隱私宣告**：使用 Preferences 時核 `PrivacyInfo.xcprivacy` 的 UserDefaults required-reason，官方建議 `CA92.1`，需符合實際用途；App Privacy 表、Privacy Manifest 與 Google Data safety 是不同項目。[Preferences 官方說明](https://capacitorjs.com/docs/apis/preferences)
- **SDK／權限**：清查最終 IPA／AAB 與所有依賴；無廣告、分析追蹤、遠端 crash SDK、AD_ID、位置、相機、麥克風或聯絡人功能。Google 兒童 App 的 SDK／API 也須適用兒童服務，不能聲稱所有 Capacitor 插件都自動取得 Families 認證。[Families SDK 要求](https://support.google.com/googleplay/android-developer/answer/9893335)
- **權利／資料**：隨包保留 Apache-2.0、NOTICE、逐張照片作者與原授權，以及原創文字／AI 情境圖的標示；圖鑑照片和想像故事區分清楚。來源授權不等於商標權授予。
- **裝置驗收**：iPhone／iPad／Android 的飛航首次開啟、旋轉、返回鍵、原生軟鍵盤、鎖屏、聲音、系統回收、更新保留資料與最低 OS 都留證據。Windows 瀏覽器代理、unsigned build 或 simulator 不等於實體裝置通過。

## 帳戶待完成事項

Google 新個人帳戶的裝置驗證需實體、非 root、Android 10+ 裝置，並由帳戶持有人登入 Play Console 手機 App；不能用 emulator 冒稱完成。使用者目前沒有 Android 機，因此先建立／驗證包，帳戶裝置與電話驗證列待辦。[Google 裝置驗證](https://support.google.com/googleplay/android-developer/answer/14316361)

若本帳戶屬 2023-11-13 之後建立的個人帳戶，正式發佈前另需至少 12 位測試者連續加入封閉測試 14 天，再申請 Production access。帳戶適用性與完成狀態尚待 Play Console 確認，不從另一個 App 的進度推定本 App 已完成。[Google 封閉測試](https://support.google.com/googleplay/android-developer/answer/14151465)

此 Windows 工作環境沒有實體 Mac；本 repo 正在準備 `macos-26` GitHub Actions 的 unsigned iOS simulator App／archive 編譯，尚未宣稱成功。取得本遊戲成功 build 後，再依 [iOS 建置文件](native-ios.md) 完成簽署與 TestFlight。這一輪不新增帳戶、付費、操作另一個 App 的簽章流程或上傳。

商店草稿位於 repo 的 `store-listing/zh-TW/`；它們是送審維護稿，不是 App 內已公開的隱私政策頁。最終發布者需核實平台表單、權利與適用兒童隱私法規；本文件不作法律或獲審保證。
