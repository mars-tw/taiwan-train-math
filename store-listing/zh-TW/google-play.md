# Google Play 繁體中文草稿

更新：2026-10-06。原生離線、儲存與外連門檻需 final release AAB 驗收後再提交本稿。

原生 **1.0.0／build 1**，Web **1.11.0**。Android release APK／AAB 已使用這款遊戲獨立金鑰簽署並核驗，Google Play 尚未上架。iOS 已完成 Xcode 26.6／SDK 26.5 原生編譯，Apple 正式簽署及 TestFlight 尚待設定。

本遊戲的獨立 Android 上傳金鑰已建立，私檔在 repo 外並登記 live source；尚未把它當成已簽署 release 證據。Apple 的另一遊戲私鑰授權不適用本遊戲。

| 欄位 | 草稿／狀態 |
| --- | --- |
| App 名稱 | 小小列車長 |
| 公開開發者名稱 | MARS_TW，已由使用者確認 |
| Package name | tw.mars.trainmath，平台建立待確認 |
| 客服 email | a820628a@gmail.com |
| App 或遊戲／類別 | 遊戲；教育類，最終 Console 設定待確認 |
| 目標年齡 | 建議 5 歲以下、6–8 歲，按最終包填寫；不因家長陪玩勾選成人群組 |
| Ads | 無；需確認所有 final 依賴與 manifest 沒有廣告行為 |
| IARC 評級問卷 | 未完成，不能直接宣稱已評為 Everyone 或 PEGI 3 |
| 支援網址 | https://mars-tw.github.io/taiwan-train-math/support.html，2026-10-06 已部署，HTTP 200 |
| 原生隱私網址 | https://mars-tw.github.io/taiwan-train-math/privacy.html，2026-10-06 已部署，HTTP 200 |
| versionName／versionCode | 1.0.0／1；Web 1.11.0 為獨立版本 |
| release 簽署、發布地區／價格 | 尚未完成／設定 |
| 身分／電話／裝置驗證 | 身分已完成；電話與裝置仍待，本輪不代辦 |

## 短描述

認識台灣火車，玩數數、拼圖和二十種小任務，親子一起慢慢探索。

名稱 30 字元、短描述 80 字元、完整描述 4,000 字元；只複製各欄位本文，不含本稿的待核說明。[Google 欄位限制](https://support.google.com/googleplay/android-developer/answer/9859152)

## 完整描述

小小列車長是給 3–8 歲親子一起玩的繁體中文火車遊戲。

先數一數月台上的乘客，再慢慢嘗試更多玩法。二十種小任務分為數學、觀察與記憶、拼搭與方向、生活與分享：數數、簡單加減、排序、比較、規律、看時鐘、列車辨認、翻卡配對、照片拼圖、分類、迷宮、接軌道、排指令、配重量、拼圖形、找不同、裝貨、分享、尋寶與車票點數搭配。

每題有短短的目標和操作方向。提示教方法，答案由孩子自己找；答錯可以再試，沒有倒數壓力。難度依理解程度調整，不把年齡當成考試。

圖鑑有 59 個列車與名稱條目，使用 58 張核對過的實車照片，沒有正確照片的車號標為待補。四段星光高鐵故事則是想像情境，可以暫停、重播和切換章節。完成任務後，讀一句列車或真實台灣風景的小發現，再收藏紀念章和小禮物。

原生版的遊戲、照片與故事隨 App 安裝，可離線遊玩。不設帳號、廣告、付費購買或分析追蹤；護照留在這台裝置，不提供帳號同步。可用本機中文語音時才朗讀，也可以完整靜音玩。

作者、資料與照片授權在 App 內保留，離開 App 的連結需由成人完成乘法關卡後才開啟。本遊戲為非官方教育專案。

## Console 準備

新手機／平板 App 需 target API 36+；Families、Data safety、App access、內容評級均依實際 release AAB 填寫。此產品無登入，App access 可說明不需帳號，另提供家長門檻實際操作方式。[API 要求](https://support.google.com/googleplay/android-developer/answer/11926878)、[Families](https://support.google.com/googleplay/android-developer/answer/9893335)

成人乘法關卡只攔截離開 App 的連結，不是身分驗證，也不代表法律同意。客服與公開資料沿用 MARS_TW／a820628a@gmail.com；帳戶裝置與電話驗證限制仍需按 Play Console 完成。

帳戶若屬適用的新個人帳戶，須完成 12 位測試者連續 14 天的封閉測試及 Production access 申請；不能用另一 App 的測試或 emulator 代替裝置驗證。[封閉測試](https://support.google.com/googleplay/android-developer/answer/14151465)、[裝置驗證](https://support.google.com/googleplay/android-developer/answer/14316361)

## Windows release 簽署重跑

使用 JDK 21、Android Build Tools 36，先產生 `assembleRelease`／`bundleRelease` 輸入，再由授權憑證流程設定當次 process environment 的 `TRAIN_MATH_STORE_PASSWORD` 與 `TRAIN_MATH_KEY_PASSWORD`。不要把密碼值打進原始碼、CLI 引數或日誌；以下只有參數位置，未提供秘密值。

```powershell
& ./scripts/sign-android.ps1 `
  -KeyStoreFile '<repo 外已登記的本遊戲 keystore>' `
  -KeyAlias '<本遊戲已登記的 alias>' `
  -BuildToolsDirectory '<本機 Android Build Tools 36 目錄>'
```

腳本用 `apksigner`／`jarsigner` 簽署與核驗，輸出版本 1.0.0 的 APK／AAB 及 `signed-artifacts.json`。是否成功以 root 讀回簽章、App ID、版本／build、hash 為準，不因金鑰建立或文件提供命令就宣稱成功；本輪未操作商店。
