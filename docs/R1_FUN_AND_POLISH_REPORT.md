# R1 好玩＋美觀優化報告（Web 1.12.0）

日期：2026-10-15
執行：Claude Code 本機直接修改，未使用 Codex，未開任何可見視窗（Playwright 全程 headless Chromium，Blender 未開）。
計畫：[`OPTIM_PLAN_R1.md`](OPTIM_PLAN_R1.md)

## 結論

老闆要的「好玩、美觀」，這輪抓了四個最直接的問題來修：

1. 首頁一打開看不到「出發」按鈕：四種視口都要往下捲 1000px 以上。現在故事區首屏就有大顆「🚆 開始玩！」。
2. 答對、答錯幾乎沒有回饋：答對只有一行灰綠小字，答錯沒聲音。現在答對有打勾、彩帶星星、鼓勵語、金星和音效；答錯則輕輕搖一下，配暖色提示和柔和提示音。
3. 桌機 1366×768 要捲動才按得到答案：現在底部操作列固定在畫面下緣。
4. 乘客沒有臉、顏色灰：現在有眼睛、腮紅、笑臉，衣服換成明亮色票，全部通過亮度和飽和度閘門。

## 逐項結果

| # | 計畫項目 | 狀態 | 證據 |
|---|---|---|---|
| 1 | 首頁大開始鈕 `#hero-play` | 完成 | `after-audit.json` `heroInView`：桌機 top 438／768、1366×600 為 438／600、手機直式 283／844、橫式 263／390、平板 423／768，全部在首屏；before 的出發鈕在 1005–1065px |
| 2 | 桌機底部操作列 sticky、矮螢幕壓縮 | 完成 | `answersInView` 與 `nextInView` 五種視口全部為 true（before 桌機答案在 y≈747 以下被切掉） |
| 3 | 答對慶祝（打勾、彩帶、鼓勵語、金星、音效） | 完成 | `after-*-4-correct.webp`；`tests/celebration.test.mjs` |
| 4 | 答錯鼓勵（輕搖、暖色提示、柔和音） | 完成 | `after-*-3-wrong.webp`；提示音音量 0.035，低於答對音 0.06，只用 sine 波 |
| 5 | 過程小獎勵音（配對、尋寶、找不同、數數記號） | 完成 | `cue("pop")` 三處、`cue("tick")` 一處；測試檢查長度 ≤0.3／0.1 秒 |
| 6 | 進度小列車換站滑動、完成站金星 | 完成 | `after-*-2-game.webp`；用 Web Animations 從上一站位置滑過來，減少動畫時不播放 |
| 7 | 終點蓋章、星星、慶祝短曲 | 完成 | `after-*-5-finish.webp`；星星數＝站數（測試） |
| 8 | 出發汽笛 | 完成 | `depart()` 開頭 `cue("whistle")`；音效關閉時不播放 |
| 9 | 乘客加臉、明亮衣服 | 完成 | 色票 `#f28c38 #2f9ad6 #58b368 #e2577f #8d63d2 #e0b31f`，測試以 HSL 驗證飽和 ≥0.32、亮度 0.30–0.75 |
| 10 | 糖果按鈕、題目區天空漸層 | 完成 | before/after 截圖對照 |
| 11 | 小按鈕放大到 48px | 完成 | `after-audit.json` 五種視口首頁、遊戲、終點、遊戲室「小於 44px」清單全部為空（before 桌機遊戲畫面有 6 項、手機直式 1 項） |
| 12 | 減少動畫與不擋點擊 | 完成 | `after-reduced-motion-correct.webp`：`reducedMotion: "reduce"` 下特效層數量 0、文字回饋照常；CSS 測試確認 `pointer-events: none` |

## 試玩中發現並修掉的問題

- 彩帶粒子飛出面板邊緣，會讓手機頁面出現橫向捲動，畫面被縮放，連帶讓「抵達終點」按鈕的點擊落點偏掉。這是 headless 效能腳本在手機模擬第二趟時抓到的。修法：特效層蓋滿面板並 `overflow: hidden` 裁切。修後五種視口答對後 `overflowAfterCorrect` 都是 false，另加 CSS 測試防回歸。
- 開始鈕原本用整顆按鈕上下呼吸，Playwright 判定元素「不穩定」，小孩手指也比較難瞄準。改成按鈕不動，只讓外圈光暈擴散。
- 建置腳本會把整個 `docs/` 複製進 `dist/` 與 App 套件，優化輪截圖會一起被打包。改成跳過 `docs/evidence/`，並加建置測試。`dist` 檔案數由 247 降到 190。

## 全遊戲冒煙測試

headless 手機直式，三種難度各從遊戲室啟動每一個可玩遊戲（3–4 歲 17 種、5–6 歲 20 種、7–8 歲 20 種，共 57 次啟動），能按答案的先按第一個選項，再按「一起想一想」：

- page error：0
- 橫向溢出：0

腳本只檢查能否進入、按答案與提示不出錯，不代表 20 種玩法的每一步都重新手動驗證過。

## 品質閘門

| 閘門 | 結果 |
|---|---|
| `npm test`（Pages 與 native workflow 實際執行的同一支） | 223 項全過，0 失敗（原 213 項，新增 10 項：`celebration.test.mjs` 9 項、`build.test.mjs` 1 項） |
| `npm run build`（Pages workflow 執行） | 成功，190 個檔案 |
| 效能 p95（headless Chromium，桌機 1366×768 與手機 390×844 DPR2，各三跑取中位） | 桌機：首頁故事 16.8ms、答對慶祝 16.7ms、終點 16.7ms；手機：16.7／16.8／16.8ms。全部 ≤18ms。數據在 `evidence/r1/perf-after.json` |
| 秘密掃描 `sk-proj-…`／`sk-…40` | 排除 .git、node_modules 後 0 命中 |
| 版本 | Web 1.11.0 → 1.12.0（package.json、lock、index.html 快取參數與頁尾、所有模組 import、trip-session `GAME_VERSION`）；1.11.0 的未完成旅程仍可接回（測試已涵蓋） |
| 外部請求 | 四種視口全程 0 個非本機請求；沒有新增外部連結、追蹤或廣告 |
| 家長區 | 未修改 `native-parent-access.js`、家長設定門檻與外連關卡 |

效能量測限制：headless Chromium 的 rAF 以 60Hz 節拍回報，16.7ms 代表沒有掉幀，但無法反映實體低階手機的 GPU 負載；也沒有開 CPU 降速。實機數據需要另外量。

## 版本號殘留（刻意保留）

`git grep 1.11.0` 還有以下位置，都是記錄「已送審原生 App 包的是 Web 1.11.0」的商店或歷史文件，依指示不碰商店：

- `.github/workflows/ios-store-screenshots.yml`（第 101、131 行檢查 `webSourceVersion == '1.11.0'`）
- `store-listing/zh-TW/*.md`、`docs/app-store-preparation.md`、`docs/native-ios.md`
- `CHANGELOG.md`、`docs/validation.md` 的 1.11.0 歷史段落
- `android/variables.gradle` 的 `androidxActivityVersion = '1.11.0'`（AndroidX 套件版本，與本遊戲無關）
- `src/trip-session.js` 與測試中，相容舊存檔用的 `"1.11.0"`

**風險**：下次執行 `ios-store-screenshots.yml` 時，`dist-native` 的 `webSourceVersion` 會是 1.12.0，第 101 行的檢查會失敗。下次要拍商店截圖或送新 build 前，需要有人決定是更新該 workflow，還是用 1.11.0 的 commit 建置。本輪沒有修改或觸發任何 workflow。

## 素材與授權

- 沒有新增任何圖片、音檔或字型。音效全部用 Web Audio 振盪器在裝置上即時合成（`src/celebration.js` 的 `SOUND_CUES`），程式碼採 Apache-2.0，不需要另記 CREDITS。
- 沒有使用本機 AI 派工器的 `music` 能力，所以 ASSET-LICENSE 不需要更新。

## 缺件與下一輪建議

1. **背景音樂**：本輪只做短音效。BGM 需要另加開關、音量與檔案大小評估；可用本機派工器 `music` 產生，並記錄來源。
2. **新 2D 原畫**：老闆指定 gpt-image-2，本輪拿不到，未新增。乘客只做 SVG 精修；列車照片、故事插圖維持原樣。
3. **收集動機**：這輪只在終點顯示「這趟幾顆星」，沒有累積星星或新的收藏機制（會動到本機存檔格式與 PRIVACY.md，需另外評估）。
4. **其他 19 種玩法的專屬回饋**：通用回饋（打勾、彩帶、鼓勵語、提示音）對所有玩法都生效；但「選錯的答案搖一下」只作用在有選項按鈕的玩法（數數、比較、規律、時鐘、認車）。拼圖、迷宮等玩法答錯時是提示列搖動和變色。
5. **實機與真實兒童試玩**：本輪只有 headless 模擬，觸控手感、音量大小和小孩是否真的看懂，還需要實體手機或平板與親子試玩確認。
6. **原生 App**：本輪只改 Web。原生 App 包要等下次 `native:sync` 與送審流程，才會帶入這些改動。

## 證據檔

全部在 `docs/evidence/r1/`（WebP）：

- `before-{desktop,portrait,landscape,tablet}-{1-home,2-game,3-wrong,4-correct,5-finish,6-playroom}.webp`
- `after-{desktop,desktopShort,portrait,landscape,tablet}-…` 同上（`desktopShort` 為 1366×600，before 沒有拍這個視口）
- `after-reduced-motion-correct.webp`
- `before-audit.json`、`after-audit.json`、`perf-after.json`
