# 優化輪 R1 計畫：好玩＋美觀（Web 1.12.0）

日期：2026-10-15
依據：`~/.claude/skills/game-optimization-round/SKILL.md` 八大面向與固定品質閘門、`遊戲/CLAUDE.md`、README、CHANGELOG、PRIVACY.md、docs 既有文件。
本 repo 沒有 `docs/AUDIT_full.md`、`AGENTS.md`，也沒有先前的 `OPTIM_PLAN_R*`，所以本輪編號為 R1。

## 本輪限制

- 老闆指示「不要啟動試玩，僅背景工作」：只用 headless Playwright（Chromium）與 Node 測試，不開任何可見視窗、不開 Blender。
- 不用 Codex，不用 Codex imagegen，不新增 AI 2D 原畫，不用 Blender MCP。只做：精修既有素材、程式化特效、UI 樣式、動畫節奏、程式合成音效。
- 不新增外部連結、追蹤、廣告；家長區門檻不變（`native-parent-access.js`、家長設定、外連關卡都不動）。
- 不修改、不觸發 `.github/workflows` 下任何 workflow；不碰 release、商店資料（`store-listing/` 既有未提交改動保留不動）。
- 只做本地 commit，不 push、不部署。

## 基準量測（before，headless Chromium，port 5109）

腳本：scratchpad `capture.mjs`；截圖與 `before-audit.json` 在 `docs/evidence/r1/`。

| 問題 | 證據 |
|---|---|
| 首頁四種視口都看不到「出發」主按鈕，要往下捲 1000px 以上；首屏只有一個 13px 的「開始旅程 ↓」文字連結 | `before-audit.json` 的 `startInView`：桌機 top 1065／視窗 768；手機直式 1005／844；橫式 1039／390；平板 1050／768 |
| 桌機 1366×768 進遊戲後，答案按鈕在畫面外，要捲動才按得到；答對後「前往下一站」也在畫面外 | `before-desktop-2-game.png`、`before-desktop-4-correct.png` |
| 答對只有一行灰綠小字和三聲短音，選中的答案沒有標示，答案按鈕全部變灰，像是「停用」而不是「答對」 | `before-*-4-correct.png` |
| 答錯沒有聲音，回饋框和一般提示同色，看不出「再試一次」 | `before-*-3-wrong.png` |
| 進度列只有數字圓圈，看不出列車往前開 | `before-*-2-game.png` |
| 終點畫面靜態，沒有慶祝感 | `before-*-5-finish.png` |
| 乘客圖沒有臉，衣服顏色灰（#698b93 飽和約 0.17、#a6a081 約 0.17、#ac817a 約 0.23），低於飽和閘門 0.32 | `src/app.js` `person()` |
| 桌機頁首語音鈕、遊戲內聽題目／全螢幕鈕 42×42，小於 44；導覽「首頁」寬 28px | `before-audit.json` `homeSmall`／`gameSmall` |

## 計畫清單（逐項可驗收）

| # | 面向 | 項目 | 驗收方式 |
|---|---|---|---|
| 1 | 選單／按鈕 | 首頁故事區加大顆「🚆 開始玩！」主按鈕（`#hero-play`），行為與出發小站的主按鈕相同（第一趟先玩數數）；原「開始旅程 ↓」保留為次要連結 | 四視口 `#hero-play` 完全在首屏內；單元測試確認 story 標記有且只有一個 `hero-play`、app 綁定同一出發流程 |
| 2 | 按鈕 | 桌機遊戲中，底部操作列改為 sticky，答案與「前往下一站」不必捲動；矮螢幕（≤920px 高）壓縮題目區間距 | 1366×768、1366×600 進遊戲後答案按鈕完全在視窗內（after-audit） |
| 3 | 技能回饋 | 答對：選中答案亮綠＋✓、隨機鼓勵語（太棒了／好厲害…）、彩帶星星爆發、目前站點變金星、四音上行音效 | 截圖；`celebration.test.mjs` 驗證粒子數上限、減少動畫時不出粒子、音效音量與長度上限 |
| 4 | 技能回饋 | 答錯：選錯的答案輕輕搖一下、回饋框改暖黃色「差一點點」語氣、柔和兩音下行提示音；不扣分、不計時 | 截圖；測試確認提示音音量低於答對音、只用 sine 波 |
| 5 | 技能回饋 | 過程小獎勵：記憶翻到一對、尋寶找到一個、找不同找到一處時播放短促「啵」聲 | 程式審查；測試確認 cue 存在且長度 ≤0.3 秒 |
| 6 | 動作流暢度 | 進度列加一台小列車，換站時沿軌道滑到下一站；完成站顯示金星 | 截圖；減少動畫時不播放滑動 |
| 7 | 美術／好玩 | 終點畫面：紀念章「蓋章」落下、彩帶、凱旋短曲、顯示本趟收集的星星數 | 截圖；測試確認星星數＝站數 |
| 8 | 好玩 | 出發時播放雙音火車汽笛聲（只在音效開啟時） | 程式審查；測試確認 whistle cue |
| 9 | 人物／腳色樣子 | 乘客 SVG 加上眼睛、腮紅、笑臉；衣服換成明亮配色，全部通過飽和 ≥0.32、亮度 0.30–0.75 | `celebration.test.mjs` 以 HSL 計算衣服色票閘門 |
| 10 | 美術／按鈕 | 答案按鈕與主按鈕改成有厚度的「糖果按鈕」（底部陰影、按下下沉）；題目區背景改為淡天空漸層 | before/after 截圖 |
| 11 | 按鈕 | 頁首語音鈕、遊戲內圖示鈕放大到 48px；桌機導覽連結最小寬 48px | after-audit 中小於 44px 的項目清單 |
| 12 | 無障礙 | 所有新動畫遵守「減少動畫」設定與系統 `prefers-reduced-motion`；特效層 `aria-hidden`、不攔截點擊 | 測試＋CSS 審查 |

## 不在本輪範圍（缺件清單）

- 新 2D 原畫（角色、場景）：老闆規定用 gpt-image-2，本輪拿不到，不新增。乘客只做 SVG 精修。
- 背景音樂：本輪先以程式合成短音效補足回饋，不加 BGM。本機派工器的 `music` 能力可用，但 BGM 需要另加開關、授權記錄與檔案大小評估，留待下一輪。
- 3D／Blender 相關面向（三視圖、骨架動畫）：本遊戲是 2D 網頁教育遊戲，沒有 3D 角色，不適用。
- 實機觸控與真實兒童試玩：本輪只能 headless 模擬。

## 品質閘門

- `npm test`（Pages／native workflow 實際執行的就是 `npm ci && npm test`，Pages 另跑 `npm run build`）全綠。
- 新功能測試：`tests/celebration.test.mjs`、`tests/home.test.mjs` 補項目。
- 效能：headless Chromium 首頁故事動畫與遊戲答題慶祝時的 rAF frame time p95，桌機與手機模擬各三跑取中位。
- 秘密掃描 `grep -rniE "sk-proj-[A-Za-z0-9_-]{20}|sk-[a-z0-9]{40}"`（排除 .git／node_modules）零命中。
- 版本 Web 1.11.0 → 1.12.0；原生 App 版本（1.0.0／build 3）與商店資料不動。
