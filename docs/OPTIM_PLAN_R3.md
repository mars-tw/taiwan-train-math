# R3 上架可能性優化計畫

日期：2026-10-15。狀態：PREPARED。目標版本：1.14.0。

已讀核心規則、token-efficient-ai-dispatch、game-optimization-round、上層 CLAUDE.md、R2 手機報告與計畫；本 repo 無 AGENTS.md、CLAUDE.md、AUDIT_full.md。本次工作單明確禁止派工及遠端操作，覆寫共用流程的外部委派／覆核要求。只修改本 repo，其他 repo 與 native-kit 唯讀。原有三份 store-listing 異動不納入本輪。

## 驗收項目

1. 招牌數學玩法：首頁首屏新增「拆合車廂調度台」，操作實體化座位的數量、分組與合成，三站完成一個數學目標。提供首玩教學、無限重試、即時數量回饋、暫停／重啟保存與完成紀錄。新狀態需驗證、備份相容、完成不可重複計數。
2. 兒童操作：所有兒童可操作按鈕、導覽、summary 與遊戲格子至少 60×60 CSS px；密集網格允許在題目內捲動，返回／主要操作保持可達。檢查 iPhone SE、直橫手機、大螢幕、iPad 直橫與 13 吋、矮桌機。保留既有測試，新功能新增模型及真實 UI 路徑測試。
3. 區隔證據：DIFFERENTIATION 逐一比較同帳號 13 款其他作品；比對公開同類產品的實際功能，避免宣稱全球唯一。SHARED_ASSETS_AUDIT 以檔案 SHA-256 及程式／樣式比對列重複與處理，標明標準第三方框架和未處理風險。寫出是否併入交通學院的決策建議。
4. 完整度與隱私：掃描佔位／英文／除錯殘留、網路用途與 SDK；核對 iOS manifest、Android 權限、Google 宣告及唯讀 native-kit。驗證兒童外連家長關卡、離線 payload、重開保存與背景恢復；原生實機缺驗證必列缺件。
5. 商店草稿：docs/store 放繁中名稱、副標題、說明、關鍵字、英文審查備註、真實畫面清單；headless 截取 1290×2796、2064×2752 PNG。新文案按 speak-human-tw mode 2 直接校訂，修改摘要寫報告。不修改或上傳既有提交備註。
6. 品質：npm test、既有 mobile／Python 回歸、新 reviewer E2E、web/native build、離線 package hash、版本與秘密掃描、diff check。所有效能資料標「並發載量測，僅供參考」，正式效能閘留待閒置機器驗證。
7. 證據與收尾：before／after、測試與稽核 JSON 放 docs/evidence/r3-store；docs/CODEX_RESPONSE_R3_STORE.md 區分 PREPARED／EXECUTED／VERIFIED／BLOCKED，評估 Apple 4.3 風險與合併方案；明確路徑 git add，只做本機繁中 commit。

## 八大面向與限制

美術沿用既有照片及插圖，只新增本作數學教材 UI，無法指定並確認 gpt-image-2 時不新增 raster 原畫，記錄缺件。按鈕與選單本輪實改；人物、地圖與角色三視圖沿用既有素材，無新增角色或模型。技能以數學數量守恆及完成回饋驗證，無戰鬥／消耗技能。動作保留既有動畫與減少動畫偏好，不用單圖晃動冒充新角色動畫。

Apple 退件參考已記錄本作不再獨立送審，本輪只完成本機改版及決策資料，不改變該商務決策。iOS／Android 編譯、簽章、實機測試、正式商店資料安全表單與上傳均不在本輪執行範圍。
