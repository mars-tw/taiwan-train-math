# 本輪之外的送件缺件

日期：2026-10-15。狀態：BLOCKED（送審條件），不影響已完成的本機改版。

1. **商務決策**：本作既有決策是不再獨立送 Apple。本輪建議把拆合數學作為交通學院模組；沒有修改交通學院，等待老闆決定，不能把草稿當重送指令。
2. **原生 1.14.0／build 4**：自有 iOS／Android target 已 bump；本輪只有離線 Web payload，沒有新版 IPA／AAB、簽章、Archive Privacy Report 或安裝驗證。
3. **舊 iOS workflow**：`scripts/export-ios-store.sh`、`.github/workflows/ios-store.yml` 等匯出／截圖流程仍鎖定 1.0.0／build 3 與歷史 artifact、來源 hash。本輪保留嚴格拒收條件，沒有把舊檔改標成 1.14.0；需要新的來源／hash／簽章契約後才能出新版。`native-kit/apps/taiwan-train-math` 不存在，不能借用其他款的包代替。
4. **實體裝置與兒童試玩**：無頭尺寸矩陣不證明 iPhone、Android、iPad 真機表現。待補首次安裝飛航模式、切背景／鎖屏、系統返回、低階機觸控、中文離線語音、儲存更新與孩子是否理解數學任務。新原生文字啟動頁只做 XML 驗證，Xcode 編譯／外觀待補。
5. **商店資料與素材**：Apple App Privacy、Google Data safety／Families、年齡、權利人與客服資料需依最終 binary 逐項讀回；本輪不開 Console。八張實際 UI PNG 是 headless 草稿，尺寸正確，不冒充已簽章 App 截圖。
6. **美術與聲音**：沒有可指定且驗證 gpt-image-2 slug 的產圖介面，本輪沒有新增 raster 原畫；不補填舊素材的模型名稱。跨作品音色聽感未實機比較。沒有新增音檔或不明授權素材。
7. **正式效能閘**：本輪量測全部為「並發載量測，僅供參考」。Headless rAF 間隔不能取代乾淨機況的實機 CPU／GPU p95，出貨效能閘留待總稽核。
8. **4.3／4.2.6 舉證**：新數學操作與完整測試不保證 Apple 接受獨立商品。要獨立送審仍需教材深度、真實試玩與長期內容價值，以及內容提供者／提交者關係的證據；不得宣稱換文案就解決退件。

本輪未派工、未發訊息、未啟動任何遠端 workflow、未 push、未部署、未上傳或操作商店。
