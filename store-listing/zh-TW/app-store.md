# App Store 繁體中文草稿

更新：2026-10-07。iOS 正式簽署包已驗證；真機語音與完整背景操作仍需補驗，本稿不是已獲審紀錄。

原生 **1.0.0／build 1**；Web **1.11.0**。Android release APK／AAB 已簽署並核驗；iOS 使用 Xcode 26.3／SDK 26.2 編譯，iPhone／iPad 模擬器首頁啟動補驗完成。正式 IPA 已在 workflow 37565567993 匯出，簽章、profile、entitlements 與 165 份內建檔案核對通過。

Android 使用本遊戲的獨立上傳金鑰，`scripts/sign-android.ps1` 為 Windows 重跑路徑（JDK 21／Build Tools 36，密碼僅在 process environment）。Apple 使用已授權的同團隊共用 API／Distribution 憑證，搭配本遊戲獨立 profile；私密資料全放在程式庫外。

## 欄位

| 欄位 | 草稿 |
| --- | --- |
| 名稱 | 小小列車長 |
| 副標題 | 台灣火車圖鑑與數學遊戲 |
| 主要語言 | 繁體中文（台灣） |
| Bundle ID | tw.mars.trainmath，Apple App ID 6819930616 |
| SKU | taiwan-train-math |
| 主要類別建議 | 教育；次要可選遊戲，最終由發布者設定 |
| Made for Kids／Kids 年齡段 | 建議參與；尚未設定適用分組 |
| App Store 年齡評級 | 未完成當前問卷，不硬填 4+ 或其他等級 |
| 客服／Review email | a820628a@gmail.com |
| Apple Seller、Review 姓名／電話 | 未設定；不以 Google 的公開名稱推定 |
| 支援 URL | https://mars-tw.github.io/taiwan-train-math/support.html，2026-10-06 已部署，HTTP 200 |
| 原生隱私 URL | https://mars-tw.github.io/taiwan-train-math/privacy.html，2026-10-06 已部署，HTTP 200 |
| Version／Build | 1.0.0／1；Web 1.11.0 不填入這兩個欄位 |
| 著作權權利人、價格／地區 | 未設定 |
| Marketing URL | 可用既有網站 https://mars-tw.github.io/taiwan-train-math/，提交前核正常 |

名稱與副標題均限制 30 字元；年齡評級問卷和 Made for Kids 年齡段分別填寫。[官方欄位定義](https://developer.apple.com/help/app-store-connect/reference/app-information/app-information/)

## 宣傳文字草稿

陪孩子認識台灣火車，從數數開始，慢慢試拼圖、分類和方向。每題只給方法提示，自己試一試；答對後，再認識一個列車或台灣風景的小知識。

## 完整描述草稿

搭上星光高鐵，和孩子一起看看山海、認識火車，也練習數學。

小小列車長適合 3–8 歲親子同玩，以繁體中文帶孩子從數數開始。二十種玩法分成數學、觀察與記憶、拼搭與方向、生活與分享，按理解程度換難度。題目會輪替，答錯可以再試，沒有倒數壓力。

- 數乘客、算上車下車、排序、比較、找規律和看時鐘。
- 拼火車照片、整理行李、走迷宮、接軌道、排方向指令。
- 分享點心、配重量、用代幣付剛好的車票點數。
- 閱讀 59 個列車與名稱條目，欣賞 58 張核對過的實車照片；尚未取得正確照片的條目明確標示待補。
- 看四段星光高鐵的想像故事，開啟信封中的故事任務；答對後再讀一句真實列車或台灣地理小發現。
- 收集旅程紀念章及 36 款小禮物，所有玩法不靠購買解鎖。

原生版將遊戲、故事和照片放在 App 裡，安裝後可離線玩。護照與未完成操作保留在這台裝置，不設帳號、不提供跨裝置同步。沒有廣告、付費購買或分析追蹤。

語音可關閉，完整遊戲可靜音使用；只有裝置具備可用的本機中文語音時才朗讀。離開 App 的來源與授權連結，需由成人完成乘法關卡後才開啟，不是孩子過關的條件。

這是非官方教育專案。故事山海圖與星光高鐵是想像情境；圖鑑實車照片、作者與授權分別列明。

## 關鍵字候選

火車,台灣,數學,數數,加減,拼圖,分類,迷宮,親子,圖鑑,方向,分享

僅在按兒童產品設定 Made for Kids 並完成檢查後，使用本稿中的兒童定位文案；不要以改成成人分類迴避原產品定位。參考 [Apple Kids](https://developer.apple.com/kids/)。

送審備註需說明成人乘法關卡只攔截離開 App 的連結，不是身分驗證或法律同意。共用帳戶授權已完成；每款 App 的包、profile 與審查證據仍各自核對。
