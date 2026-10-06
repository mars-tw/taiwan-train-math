# 原生 App 隱私／Data safety 待核稿

更新：2026-10-06。公開客服：a820628a@gmail.com。Google 公開開發者為 MARS_TW；Apple Seller／法定發布者姓名尚未確認。本稿不是已提交的商店隱私宣告。

版本為原生 **1.0.0／build 1**、Web **1.11.0**。公開政策採 https://mars-tw.github.io/taiwan-train-math/privacy.html，支援採 https://mars-tw.github.io/taiwan-train-math/support.html；兩頁已在 2026-10-06 部署並實測 HTTP 200，含 MARS_TW 與公開客服信箱。

## 預定原生隱私文字

小小列車長不要求帳號、姓名、生日、email、位置或兒童照片。遊戲不設廣告、付費購買、聊天或分析追蹤。

難度、聲音設定、集章、禮物、最近玩過的任務，以及未完成旅程的操作保存在裝置上。遊戲不主動上傳這些紀錄，也不提供帳號同步；系統備份依作業系統與裝置設定處理。算術輸入、錯答文字、家長門檻結果不作持久保存。家長可以清除本機紀錄。

家長可主動下載護照備份，再選擇檔案匯入另一裝置；備份僅含遊戲紀錄及經驗證的續玩配方，不自動上傳，匯入取代對應本機紀錄前會再次確認。

遊戲資料、照片與故事隨 App 提供，不為顯示照片向來源網站請求檔案。原生版不使用遠端 Web Speech；只有已安裝且確認可在本機處理的語音才朗讀，缺語音時繼續靜音玩。不使用麥克風、不錄音、不把兒童聲音送出去。

離開 App 的資料、作者或授權連結，會先要求成人完成乘法關卡，才在系統瀏覽器視窗／瀏覽器開啟；可取消返回。乘法關卡不驗證身分，也不是法律上的同意，題目及結果不寫入護照。外部網站及裝置供應商有自己的政策，遊戲不把練習紀錄附加到網址。若家長主動寄信客服，對方可收到家長自行提供的信件內容；請不要在來信中附兒童姓名、照片或不需要的識別資料。

最終原生包、備份設定及客服處理方式必須與已公開的 `privacy.html` 一致；頁面部署不代表已完成商店申報。

## 商店表單建議與成立條件

| 項目 | 候選回答 | 提交前證據 |
| --- | --- | --- |
| Apple App Privacy：Data Collected | Data Not Collected | App 與所有 SDK 不把可存取的使用者資料傳出裝置；不能只查 web 原始碼 |
| Apple Tracking | No | 無 IDFA／廣告歸因／第三方跨服務追蹤 |
| Google Collected／Shared | No／No | 最終 AAB 的 SDK、權限、連線與跨 App 資料行為符合；本機處理不當成對外蒐集 |
| 位置、識別碼、兒童姓名／生日、照片／麥克風 | 無功能／無蒐集 | 沒有相關權限、API 或 SDK 默默執行 |
| App activity／Diagnostics | 不由遊戲上傳 | 無遙測或遠端 crash reporter；測試資料不混入 production SDK |
| 帳號建立／刪除 | 無帳號；清除本機紀錄 | 不填虛構的帳號刪除 URL；檢查 Console 真正要求哪些欄位 |
| 傳輸加密 | 無 App 使用者資料傳輸時不作虛構承諾 | 依 Console 當下顯示的問題回答；若加入出網服務重做資料盤點 |
| 公開隱私 URL | https://mars-tw.github.io/taiwan-train-math/privacy.html | 2026-10-06 HTTP 200、免登入可讀；送件前再核實與最終包一致 |

Apple 以資料是否離開裝置且可被開發者／合作方持續存取判定蒐集；Google 的僅本機處理可不作對外蒐集申報，但仍須完成表單並檢查 SDK。兩者都不能以一份「無資料」文字替代 binary 核對。[Apple App Privacy](https://developer.apple.com/app-store/app-privacy-details/)、[Google Data safety](https://support.google.com/googleplay/android-developer/answer/10787469)

若使用 Capacitor Browser，iOS 會採 `SFSafariViewController`，不能把行為寫成一定切到獨立 Safari App。外連仍要通過家長操作，並在開啟前停掉遊戲聲音。Google 對自行控制的 WebView 內容與使用者瀏覽公開網站有不同申報規則，按最後的外連實作核對；不宣稱打開第三方網站後仍完全沒有網路流量。[Browser 官方行為](https://capacitorjs.com/docs/apis/browser)、[Google WebView 說明](https://support.google.com/googleplay/android-developer/answer/10787469)

## Native 盤點記錄待填

- 原生 version／build：1.0.0／1；Web：1.11.0。final IPA／AAB 的 SHA-256：待正式簽署包填寫。
- 建置狀態：Android release APK／AAB 已編譯、簽署並核驗；iOS Simulator App／未簽 device archive 已編譯並核對內建 PrivacyInfo，Apple 正式簽署與啟動補驗仍待完成。
- 本遊戲獨立 Android 上傳金鑰已建立並在 repo 外登記 live source；`scripts/sign-android.ps1` 需 JDK 21／Build Tools 36，密碼僅在 process environment。簽章核驗不代表商店上架或 OS 服務網路行為已驗收。
- 20 種遊戲飛航首次安裝／重新開啟結果：待實機驗收。
- Release 網路盤點，含有／沒有本機中文語音：待記錄；不將本機 `capacitor://`／WebView asset 讀取當成遠端服務。
- 背景／鎖屏停音、原生儲存失敗、清除與更新結果：待記錄。
- 最終 SDK／權限清單與 native backup 設定：待記錄。
- `PrivacyInfo.xcprivacy`／UserDefaults required-reason 與 build Privacy Report：待記錄；Preferences 官方建議 `CA92.1`，用途須符合。[官方插件要求](https://capacitorjs.com/docs/apis/preferences)
- `privacy.html`／`support.html` 已在 2026-10-06 驗 HTTP 200；Apple Seller／權利人名稱與客服保留／刪除方式仍待核對。另一遊戲的 Apple 私鑰授權僅限彼遊戲，不共用到本 App。

兒童家長關卡只攔截離開 App 的連結，以成人乘法作答放行；不是身分驗證或法律同意機制，也不提供法律合規保證。[Apple 5.1.4](https://developer.apple.com/app-store/review/guidelines/#kids)
