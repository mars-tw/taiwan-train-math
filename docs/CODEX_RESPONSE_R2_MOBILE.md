# R2 手機內容與操作優化回覆

日期：2026-10-15。Web 版本：**1.13.0**。基準 commit：`c8a2a29`。計畫：[`OPTIM_PLAN_R2.md`](OPTIM_PLAN_R2.md)。本輪只改本 repo、只做本機提交。

## 改了什麼

| 項目 | 狀態 | 實作與證據 |
|---|---|---|
| 四章小站任務冊 | VERIFIED | `src/fieldbook.js`；月台準備、野餐補給、沿路找朋友、平安送到站，各三個目標；三種年齡各自保存，共 36 格。不是新增 36 種遊戲，而是把既有適齡玩法接成循序目標。`tests/fieldbook.test.mjs` 用每目標 12 個種子生成實際題目（432 趟），驗證每個目標均可生成。 |
| 真正可進入與完成 | VERIFIED | 遊戲室首屏一鍵出發；完成對應的完整練習旅程才前進，混合／故事旅程、未完成、已領獎旅程不計。一般練習若正好對應目前目標也計入。E2E 從真實選單啟動全部 36 個目標，並在四視口操作完成第一章，不直接呼叫遊戲內答案函式。 |
| 收藏與下一局 | VERIFIED | 每三格取得一枚章，每種難度四枚，合計 12 枚章；完成頁顯示章節結尾與下一目標，可直接開始或休息。護照讀回收藏，既有信封與禮物仍照常領取。`after-*-chapter-reward.png`、`after-*-passport.png`。 |
| 儲存與相容 | VERIFIED | 舊護照新增預設 0 格；上限與型別驗證；沿用既有本機儲存、原生原子偏好、備份與清除。未增加日期、登入連勝或個資。1.12.0 未完成旅程可接回，既有歷史題目配方測試保留。`tests/fieldbook.test.mjs`、`tests/trip-session.test.mjs`；`PRIVACY.md`、`privacy.html` 更新。 |
| 兒童觸控與可達性 | VERIFIED | 新任務按鈕 48px 以上；所有遊戲區／作答列按鈕最少 48px；返回固定在上方。橫向手機縮短任務冊留白，首屏看得到開始鈕。作答列高度納入捲動留白，修正桌機排車廂被擋住、重分鈕只有 26px 寬的問題。`tests/mobile.e2e.mjs`、`after-audit.json`、`after-*-scrolled-game.png`。 |
| 截圖 workflow 版本 | VERIFIED | `.github/workflows/ios-store-screenshots.yml` checkout 後從 `package.json` 讀 Web 版本，回報 manifest 實際版本；保留已驗證 run／commit／ZIP／manifest 雜湊、檔案數與裝置規格。測試目前版／未來版、舊版拒收與 hash 篡改。沒有啟動 workflow。 |
| CI 回歸入口 | EXECUTED | Pages workflow 新增安裝 headless Chromium 與 `npm run test:mobile`；只改本機檔案，未執行遠端 CI。 |

## 八大面向對照

| 面向 | 本輪結果 |
|---|---|
| 美術 | EXECUTED：沿用既有色盤，新增任務冊、進度與文字收藏章 UI；沒有新增原畫、角色或模型。 |
| 按鈕 | VERIFIED：四視口檢查按鈕尺寸、遮擋、溢出、操作與捲動後返回；手機用 touch，桌機用 mouse。 |
| 選單 | VERIFIED：任務冊每次只顯示目前目標；首屏可開始；完成頁可接下一目標或返回；原 20 種玩法仍自由開放。 |
| 人物 | 本輪不改；沿用 R1 乘客與辨識素材，既有測試保留。 |
| 地圖模型 | 本輪不新增；沿用真實列車照片、既有軌道與教材。 |
| 技能 | VERIFIED：新增循序學習／章節回饋；無消耗技能、限時或扣分；提示不影響獎勵。 |
| 腳色樣子 | 本輪無新角色；原亮度／飽和度測試照跑，無新增三視圖。 |
| 動作流暢度 | 本輪不新增角色動畫；保留逐步播放、減少動畫與現有回饋測試；未以單圖晃動冒充動畫。 |

## 自動驗證與證據

所有瀏覽器均 `headless: true`。Node／Python 及建置均在背景執行。未開啟遊戲可見視窗、瀏覽器視窗或 Simulator。

| 指令／檢查 | 結果與證據 |
|---|---|
| `npm test` | 228／228 通過（原 223 項保留；新增 5 項，內含 432 趟題目生成與 36 格完成／防重複斷言）；`unit-tests.txt`。 |
| `npm run test:mobile` | 9／9 通過；36 個目標選單啟動、四視口各 57 次適齡玩法啟動（228 次）、四次完整第一章、暫停／重載同題、禮物扣一次與收藏章讀回；`mobile-e2e.txt`、`e2e-audit.json`。57 次檢查包含題目啟動、提示、按鈕尺寸與返回，不表示完整解完所有 20 種玩法。 |
| `python -m unittest discover -s tests -p 'test_*.py'` | 9／9 通過（既有 6＋新增 3）；`python-tests.txt`。 |
| `npm run build` | VERIFIED：建置成功；`web-build.txt`。證據目錄不打包。 |
| `npm run native:build`、`node scripts/verify-native-package.mjs` | VERIFIED：本機離線 Web payload 建置與逐檔雜湊驗證，含 58 張已核對照片；`native-build.txt`、`native-verify.txt`。沒有編譯、簽署或安裝原生 App。 |
| 版本掃描 | VERIFIED：目前來源、快取參數與 package 為 1.13.0；1.12.0 在 active source/tests 僅剩歷史存檔接受清單與相容測試兩處。歷史報告及獨立的 axios 依賴版本不改；`old-version-scan.txt`。 |
| 指定秘密字串掃描 | VERIFIED：以 rg 執行等價正規式，含隱藏與忽略檔，排除 .git／node_modules，零命中；`secret-scan.json`。未讀取 `.secrets`。 |
| 效能 | EXECUTED：**並發載量測，僅供參考**。手機／桌機首頁各三跑、每跑 120 個 rAF 間隔，p95 三跑中位皆約 16.7ms；`perf.json`。這是 headless 幀節拍，不能代表實機 CPU／GPU 成本。出貨效能閘 **BLOCKED**，未宣稱通過。 |
| 變更檢查 | VERIFIED：`git diff --check` 無空白錯誤；只以明確路徑加入本輪變更；原三份 store-listing 未提交變更保留。 |

證據根目錄：[`evidence/r2-mobile/`](evidence/r2-mobile/)。`evidence-manifest.json` 記錄檔案大小與 SHA-256。

- before／after：`{before,after}-{portrait,landscape,desktopShort,laptop}-{home,playroom,game}.png`。
- 手機視口：390×844、844×390；矮桌機：1366×600、1280×640。手機 before／after 的 touch、視口與減少動畫設定相同；桌機 after 另用 mouse 驗證。
- 任務與獎勵：`after-*-mission.png`、`after-*-chapter-reward.png`、`after-*-passport.png`。
- 捲動返回：`after-*-scrolled-game.png`。初始截圖與遊戲 control 資料在 `before-audit.json`、`after-audit.json`。
- 最終檢視：手機直橫任務入口、章節完成、護照均已開圖檢查，文字可讀、主要按鈕可見；文字裁切自動檢查量測真正文字框，排除車廂輪子等刻意外延裝飾。

## 未完成、風險與缺件

| 項目 | 狀態 | 原因／下一步 |
|---|---|---|
| 實體 iPhone／Android 與兒童試玩 | BLOCKED | 本輪只有 headless touch／mouse 模擬。需以實機確認單手操作、聲音、系統返回、低階裝置與孩子是否理解。 |
| 乾淨機況效能閘 | BLOCKED | 其他線路同時工作；需在無並發的實機環境完成正式量測。 |
| 新角色／場景原畫 | BLOCKED | 可用產圖介面不能指定並回報 `gpt-image-2` slug。本輪未生成新 2D 素材，也未用程序化方塊冒充；`assets-r2.json` 記錄無新增素材。 |
| 新音樂／音效 | 本輪不做 | 未取得新的授權來源，沒有新增音檔；使用既有可關閉的回饋。 |
| iOS 新版商店截圖 | BLOCKED | workflow 仍釘選已驗證的歷史 run 與 hash；其舊 payload 不符合目前 1.13.0，會拒收。需要新版原生 artifact 與相符的來源／hash 契約後才能實跑，不能僅改版本字串假冒新版。 |
| 獨立 ChatGPT 對話覆核 | BLOCKED | 兩次 `devspace_chatgpt_list_workers` 實際均回 `Mcp error: -32603: Internal error`。沒有接單或回傳產物，不宣稱獨立覆核完成，也未改走其他模型或可見瀏覽器。載入 codex-claude-local-orchestrator 後按其路由保留缺口。 |

繁中文案直接套用 mode 2，原有對外文案調整 2 處：README 的目前版本由 1.12.0 改為 1.13.0（反映實作）；隱私頁的本機紀錄清單補上三種難度任務格數（準確揭露新增保存欄位）。新任務文案另將「找到旅費」改為「尋找小寶物」（符合幼齡尋寶玩法），「認出牠的名字」改為「認出是哪台列車」（避免用動物代詞描述列車）。數字、網址、既有授權與外連家長門檻保留。
