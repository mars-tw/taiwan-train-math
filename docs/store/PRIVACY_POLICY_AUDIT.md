# 隱私與兒童政策核對

日期：2026-10-15。原始碼／manifest／本機離線包 EXECUTED；最終簽章 binary 與商店申報 BLOCKED。

| 項目 | 本輪實際狀態與證據 |
|---|---|
| 帳號、個資、廣告、分析 | 無帳號、個資輸入、廣告、追蹤 SDK、評分請求或購買。`package.json`／lock 的 runtime 為 Capacitor core、App、Browser、Preferences 與自有 OfflineSpeech；沒有第三方分析或廣告 SDK |
| 本機學習資料 | `taiwan-train-math.v1` 含護照及新 `dispatch`：完成班數、教學站、年齡難度代碼、前後車人數。難度不是生日或個人年齡資料。每步保存、備份與清除一起處理，不傳出裝置 |
| 普通旅程暫存 | 原有 `taiwan-train-math.session.v1`；網頁依分頁 session，原生進原子偏好保存。新調度使用護照儲存，網頁關閉分頁仍可接續，沒有把兩種保存混稱相同 |
| iOS PrivacyInfo.xcprivacy | `NSPrivacyTracking=false`、TrackingDomains 空、CollectedDataTypes 空；UserDefaults 原因 `CA92.1`。xcodeproj 有列入 Resources。本輪不虛構新的蒐集類別 |
| Android 權限 | 自有 AndroidManifest 無 INTERNET、AD_ID、定位、相機、麥克風與通知權限；`allowBackup=false`，只有可用離線 TTS 查詢。合併後最終 manifest 仍須以 AAB 再驗 |
| 家長關卡 | 原生資料區與離開 App 的連結沿用乘法關卡，失敗不放行、背景撤銷。新增網頁非頁內連結同樣先請家長作答，離開／背景撤銷。E2E 驗錯答、背景撤銷、正確放行；以攔截 window.open 驗證目的地，未開外部視窗或發送連結 |
| SDK 使用目的 | Preferences 保存遊戲；App 接背景／返回；Browser 僅家長通過後顯示公開資料；OfflineSpeech 只在裝置有可用離線中文語音時發音。沒有帳號或遠端 crash reporter |
| 唯讀 native-kit | `game-store-publisher/native-kit/apps/taiwan-train-math` 不存在；共用 kit 的其他遊戲包不能代替本作驗收。本 repo 自有 ios/android 工程與 manifest 可核對，沒有修改 kit |
| 既有資料安全草稿 | `store-listing/zh-TW/privacy-data-safety.md` 仍含 1.11.0／1.0.0 等舊證據，作歷史參考。本輪以本文件提供更新狀態，未把舊簽章包宣稱為 1.14.0，也未接觸商店 Console |

## 網路請求逐項盤點

| 請求／機制 | 用途與範圍 |
|---|---|
| `fetch("data/trains.json?v=1.14.0")`、ES modules、CSS、遊戲圖片 | 同來源靜態教材。Web 由目前網站主機供應，主機可處理一般連線資訊；原生為包內 asset。沒有傳送護照或孩子作答 |
| 相片來源／教材來源／客服網頁 | 平時不請求外部來源；照片本機打包。家長通過關卡後才可開公開網址，第三方網站適用其政策，不承諾該網站完全不記錄連線 |
| 網頁 Web Speech | 預設關閉，開啟後是否使用遠端語音由瀏覽器／系統供應商決定；文字為固定遊戲教材。不能宣稱網頁語音必定離線。原生只使用離線語音插件 |
| 遙測／廣告／登入 API | 原始碼及鎖定依賴未發現；無頭審查路徑沒有跨來源 request。不是實機 OS 背景流量封包檢查 |

離線驗證使用 `dist-native` 每個實際檔案，Playwright network offline，僅以本機檔案回應虛擬 app origin，完成三站且沒有缺檔；另逐檔 SHA-256 核對。這證明本機 payload 可獨立運行，**不等於安裝後的 iPhone／Android 飛航測試**。Web 網站未增加 Service Worker，不承諾首次線上開網頁後能在完全斷線下冷啟動。

## Google／Apple 草稿值與缺件

資料安全草稿：Collected＝No、Shared＝No、Tracking＝No；依據是本機處理和未上傳的實作。沒有聲稱 Console 已填好。Google 即使不蒐集資料仍需要填表及隱私政策；只在本機處理可與傳出裝置區分。[Google Data safety](https://support.google.com/googleplay/android-developer/answer/10787469)

兒童目標族群為 3–8 歲，沒有廣告、購買、評分或第三方分析；外連必經家長。仍要以最後的商品年齡選項和 binary 核對 [Google Families](https://support.google.com/googleplay/android-developer/answer/9893335)、[Apple Kids](https://developer.apple.com/app-store/review/guidelines/#kids)。乘法關卡不是身分驗證或法律同意。

本作 UserDefaults 用途為保存自身遊戲偏好；`CA92.1` 與 [Preferences 官方文件](https://capacitorjs.com/docs/apis/preferences) 建議一致。最終 Archive 的 SDK privacy manifests、Privacy Report、Apple App Privacy、Google 申報、發布中的隱私 URL 內容與權利人資料均 **BLOCKED：本輪不建置簽章、不上傳、不操作商店**，需總稽核補驗。原始碼核對不代表平台已認可合規。
