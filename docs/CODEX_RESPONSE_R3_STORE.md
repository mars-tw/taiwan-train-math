# R3 上架可能性優化回覆

日期：2026-10-15。版本：**Web／原生來源 1.14.0，原生 build 4**。基準 commit：`058ad35`。計畫：[OPTIM_PLAN_R3.md](OPTIM_PLAN_R3.md)。僅修改本 repo、背景／headless 執行、本機提交；未 push、部署、派工、發訊息、啟動遠端 workflow 或操作商店。

## 上架風險與老闆決策

**Apple 4.3：高。建議優先將本作的數學模組併入交通學院，保持既有「不獨立重送」決策。** 本輪已把數學拆合做成首屏可玩的完整任務，但同帳號的兒童、列車與交通題材仍重疊；既有紀錄也顯示曾多次說明差異後仍退件。不能把修 bug、換標題或補審查備註當成 Apple 已接受重大差異。

[DIFFERENTIATION](store/DIFFERENTIATION.md) 已逐款比較另外 13 款作品的玩法、操作、畫面與族群，並查核 DragonBox Numbers／Endless Numbers 官方功能；沒有即時熱門榜資料或全球唯一證據，不宣稱數量操作是本作發明。可驗收的組合是繁中列車調度、同組乘客的加減關係、58 張列車照片與本機學習紀錄。

Apple 4.2.6 的內容提供者／提交者關係仍需老闆提供真實證據；共用 Capacitor 不是有罪或免責證明。Google 的本機品質準備有改善，但最終 AAB、Families／資料安全表單與真機仍缺驗證。未取得任何平台上架保證。政策依據及公開來源直接列於 [差異評估](store/DIFFERENTIATION.md)與[隱私核對](store/PRIVACY_POLICY_AUDIT.md)。

合併方案只是建議，**沒有修改交通學院、遷移進度、改 Bundle ID 或執行合併**。本輪可用來審閱、試玩與決策，尚非可上傳的簽章發行包。

## 三項最大改善

| 項目 | 狀態 | 實作與結果 |
|---|---|---|
| 首屏招牌數學 | VERIFIED | 「拆合車廂調度台」讓同組乘客依序裝滿、分車、算剩下，實際操作連接加減與數量守恆；有首玩教學、可逆移車、錯答重試、完成回饋與換數量。三種難度以有限的總數與分車配方循環，不虛稱無限手工課程。每次操作沿用護照保存，關閉分頁再開仍可續玩；進備份／清除，防重複計班。 |
| 兒童 60px 與直橫版面 | VERIFIED | 全部兒童按鈕與 summary 至少 60×60 CSS px，主要導覽／返回同樣放大；既有手機測試 44px 斷言提高至 60px。修正橫向手機首屏任務被擠掉、最小 568×320 完成頁被底部控制壓住，新增數量圖不得被操作列遮擋的斷言。 |
| 上架證據與兒童政策 | VERIFIED／PREPARED | 新增網頁外連家長關卡，保留原生失敗不放行與背景撤銷；2 個模板原生資源改成本作識別。逐項隱私／共享資產稽核、英文審查備註、繁中文案、8 張真實 UI 截圖與 hash 清單完成；原生外觀與商店表單仍待正式包核對。 |

## 其他完成項目

- `src/dispatch.js` 的狀態驗證拒絕非法數量與階段；高年齡提供足夠可見座位，不會顯示 14 人卻只有 10 個點。既有護照預設補欄位，普通旅程 1.13.0 歷史存檔仍可接回。
- 共用資產首次找到 6 組同 bytes：移除 Android 未使用的樣板機器人向量，改參照已有列車圖示；iOS 通用 Splash 版型改為本作數學標題。最後剩 4 組標準容器／metadata，逐檔 hash 與保留理由見 [SHARED_ASSETS_AUDIT](store/SHARED_ASSETS_AUDIT.md)。12 個其他 repo 與夜行列車歷史包全程唯讀。
- 移除首頁／圖鑑／護照／完成頁的英文裝飾標題；保留型號及授權專有名詞。runtime 沒有可見 Lorem、Sample、TODO、敬請期待或公開除錯面板。掃描區分教材 `mosaic-sample` 識別字與玩家可見的樣板文字。
- `docs/store/`、`docs/evidence/`、內部本輪報告／計畫不進遊戲 payload；原生另排除跨遊戲支援 URL 目錄。既有 Web 支援 URL 契約與測試保留。
- Web 1.14.0 與 iOS／Android 來源版號同步，package／lock／快取參數更新，iOS build 3→4、Android 2→4。舊存檔接受清單與歷史發行 workflow 例外留有理由，沒有放寬 hash／版本守門。
- Pages workflow 接入本機 native payload build 與新 reviewer 測試；僅改檔，未執行任何遠端 CI。

## 驗證結果

| 指令／項目 | 結果與證據（均在 `docs/evidence/r3-store/`） |
|---|---|
| `npm test` | **232／232 通過**；既有 228 項保留，新增三項拆合模型／保存測試與一項草稿不打包測試。`unit-tests.txt` |
| `npm run test:mobile` | **9／9 通過，60px 斷言**；36 個任務入口、四視口各 57 次適齡玩法啟動／提示／暫停（228 次），四次完整第一章與收藏保存。不是完整解完所有 20 種玩法。`mobile-e2e-60px.txt`、`mobile-regression/e2e-audit.json` |
| `npm run test:store` | **Chromium 20／20 通過**；17 組裝置設定（15 種 CSS 視口＋兩種商店像素倍率），各從冷啟動、教學、錯答、三站完成、暫停／關閉分頁再開、保存讀回；另驗兩種高年齡、背景事件模擬、家長關卡與離線包。`reviewer-tests.txt`、`reviewer-path.json` |
| WebKit 補驗 | **5 通過，離線 mock 驗證 1 項 BLOCKED**；手機 SE、最小橫屏、13 吋 iPad、較高難度／背景事件與家長關卡通過。Windows WebKit 的 `offline:true` 搭配 route.fulfill 在虛擬網址報 `WebKit encountered an internal error`；只有空白 HTML 的最小 fixture 也重現，因此推測是本機測試攔截限制，不能把它當 App 離線成功或確定的 App 錯誤。原測試與斷言未刪、未放寬。`webkit-tests.txt`、`webkit-offline-blocker.json` |
| Python 既有回歸 | **9／9 通過**；`python-tests.txt` |
| Web／native payload | `npm run native:build` 內含 Web build；**176 個檔案、58 張核對照片、remoteServer=false**，逐檔 SHA-256 驗證通過。`native-build.txt`、`native-verify.txt`。沒有編譯或簽署 IPA／AAB |
| 離線 | Chromium 在 network offline 下以本機 `dist-native` 檔案回應 app origin，首次進入並完成三站，無缺檔。原生 bridge／系統語音／真機飛航仍未驗證；Web 網站未增加離線冷啟動快取 |
| 隱私／版本／秘密 | plist 和 native XML 可解析、原始 Android manifest 無 uses-permission、資料安全草稿與實作核對；名稱 13 字、副標題 15 字、關鍵字 76 UTF-8 bytes。指定秘密模式包含隱藏／忽略檔掃描，排除各層 .git／node_modules，**零命中**。`final-checks.json`、`secret-scan.json`；未讀 `.secrets` |
| 效能 | **並發載量測，僅供參考**。手機／桌機、首頁／調度台各三跑、每跑 120 個 rAF 間隔；見 `perf.json`。不能當真機 CPU／GPU 時間，正式 p95 出貨閘 BLOCKED |
| 收據與變更 | `evidence-manifest.json` 記錄大小與 SHA-256；PNG／JSON／log 的 checkout 位元組規則加入 .gitattributes。`git diff --check` 通過；既有三份 store-listing 異動保留，不提交 |

## 截圖與草稿

[screenshots/manifest.json](store/screenshots/manifest.json) 收錄 8 張：1290×2796 手機、2064×2752 平板各四張。實際 CSS 視口分別 430×932、1032×1376，倍率 3／2。首頁、裝滿、分車、完成均由真實操作到達，無頭擷取、無合成與外加字；已讀圖檢視手機完成、平板分車與最小橫屏。**不是原生實機截圖**。

草稿：[繁中商店文案](store/LISTING_ZH_TW.md)、[英文審查備註](store/APP_REVIEW_NOTES_EN.md)、[截圖清單](store/SCREENSHOT_LIST.md)。before／after 與操作證據在 `evidence/r3-store/`；R2 歷史證據未被覆寫，新測試改寫入 R3 專屬目錄。

## 八大面向對照

| 面向 | 本輪範圍 |
|---|---|
| 美術 | EXECUTED：數量教材、調度單與原生標題 UI；沿用照片／圖示，無新 raster 原畫 |
| 按鈕 | VERIFIED：60px、首屏可達、返回與操作列、最小橫屏數量圖遮擋檢查 |
| 選單 | VERIFIED：首屏一鍵進教學，三站有終點／下一班／返回，不封鎖既有玩法 |
| 人物 | 沿用既有素材與測試；未新增角色，未假稱出新人物三視圖 |
| 地圖模型 | 無新增 3D／場景原畫；保留既有列車照片與故事素材 |
| 技能 | VERIFIED：數量守恆、合成與減法、錯答重試；無戰鬥消耗型技能 |
| 角色樣子 | 沿用既有色票回歸；沒有新角色要做亮度／飽和度或三視圖驗收 |
| 動作流暢度 | 保留既有動畫、減少動畫與 playback 回歸；新教材逐次更新數量，不用單圖晃動冒充角色動畫 |

## 未完成與缺件

完整清單：[RELEASE_GAPS.md](store/RELEASE_GAPS.md)。主要 BLOCKED 項目：

1. 老闆決定合併或獨立商品；Apple 4.3 仍高，沒有執行重送。
2. 新 IPA／AAB、Xcode 啟動頁編譯、原生真機／兒童試玩、最終 Privacy Report／SDK／權限與商店申報。
3. iOS 匯出／截圖流程仍釘選 1.0.0／build 3 與舊 artifact；新來源及 hash 契約尚缺，保持嚴格拒收，不能拿舊檔冒充 1.14.0。唯讀 native-kit 也沒有本作目錄。
4. WebKit 離線路由模擬失敗；真機離線仍待補，Chromium 的本機 payload 驗證已完成。
5. 指定 `gpt-image-2` 的新原畫與跨作音色實機比較；本輪沒有假報新素材或模型 slug，見 `store/assets-r3.json`。
6. 閒置機器的正式效能閘。所有本輪量測均屬並發載。

## 繁中文案 mode 2 摘要

直接套用，不另要求確認；下表是原有對外文案修改，新商店草稿以實作保真、不加療效或市場唯一承諾。

| 原句／位置 | 原因 | 改成什麼 |
|---|---|---|
| README「陪星光高鐵送信到海邊」作第一玩法 | 與新版首屏不符 | 先說同班乘客裝滿、分車、算剩下，再保留故事與原玩法 |
| README「首頁先看山海列車故事」 | 首屏已換數學入口 | 調度台先開始，故事與原旅程在下方 |
| README「首頁一打開就有『開始玩！』大按鈕」 | 混淆新調度與舊故事入口 | 改述原有旅程的作答回饋，不把舊 CTA 當首屏 |
| 首頁英文品牌小標 | 兒童可讀性與數學定位 | 動手拆合，數學上車 |
| THE TRAIN ENCYCLOPEDIA／MY RAILWAY PASSPORT／JOURNEY COMPLETED | 無必要英文裝飾 | 列車觀察筆記／我的學習足跡／數學旅程完成 |
| 隱私頁 10/6 日期與原本記錄清單 | 新增保存欄位須準確揭露 | 10/15，補調度階段、前後車人數與完成班數，未加個資蒐集 |
| README 1.13.0 與存檔清單 | 反映新版本及相容性 | 1.14.0，補 1.13 歷史旅程；本輪只在本機提交 |

既有客服、網址、列車型號、數字與授權不任意改寫。沒有以新命名掩飾同帳號重疊或既有退件。
