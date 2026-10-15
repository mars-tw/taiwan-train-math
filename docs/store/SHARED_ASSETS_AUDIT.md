# 共用素材與模板殘留稽核

日期：2026-10-15。狀態：EXECUTED；檔案 hash／來源比對 VERIFIED，原生視覺需待編譯驗證。

方法：`node scripts/store-audit.mjs` 唯讀比較本作 runtime 原始碼、美術、圖示及原生資源與 12 個其他 repo；另比較 native-kit 的夜行列車歷史 web payload。排除依賴、建置輸出與秘密路徑。自己本輪新增 runtime 檔亦納入。完整檔案、重複配對與 SHA-256：`../evidence/r3-store/shared-assets.json`。這是相同 bytes 與有限標記比較，沒有宣稱查出所有語意相似、AI 來源或全部版本。

## 完全相同的檔案與處理

| 本作檔案 | 與哪款重複 | 處理方式 |
|---|---|---|
| `android/app/src/main/res/drawable-v24/ic_launcher_foreground.xml` | 島嶼交通學院；原 hash `a8514094f754b099d3e55ce1d6e0b2de79db418b2eeacb0fc2a6bb0bfadef221` | EXECUTED：移除未使用的 Android 樣板機器人向量，改參照本作既有列車 foreground PNG。adaptive launcher 本來就指向該 PNG，沒有生成新原畫。更新後不再相同 |
| `ios/App/App/Base.lproj/LaunchScreen.storyboard` | 島嶼交通學院；原 hash `87a42e842164d75f39cca56a2cf743652f4d8e858f2eba12ae21a8ddcd9a21c6` | EXECUTED：通用 Splash 版型改為原生自動佈局的「小小列車長／拆合車廂，數學上車」紙色啟動畫面。XML 可解析，Xcode／真機外觀 BLOCKED |
| `android/app/src/main/res/layout/activity_main.xml` | 島嶼交通學院 | 保留並列明：Capacitor 標準 WebView 容器，非遊戲 UI／美術；最終 hash 見 JSON |
| `android/app/src/main/res/values/styles.xml` | 島嶼交通學院 | 保留並列明：Android／Capacitor 標準主題與 splash 設定；遊戲內容與首屏獨立 |
| `android/app/src/main/res/xml/file_paths.xml` | 島嶼交通學院 | 保留並列明：Android FileProvider 標準設定，沒有玩家視覺與文案 |
| `ios/App/App/Assets.xcassets/Contents.json` | 島嶼交通學院 | 保留並列明：Xcode 資產目錄標準 metadata，沒有共享圖片 bytes |

初次比對 6 組，處理後剩 4 組標準原生容器／metadata。最終 JSON 記錄每組完整 hash。本輪沒有改任何其他 repo 或 native-kit。

## 風格與程式框架逐項檢查

| 項目／檔案 | 比對結果 | 處理方式與剩餘限制 |
|---|---|---|
| `src/styles.css`、全部遊戲 CSS／JS | 未發現與其他已掃描 repo 完全相同的 runtime stylesheet／遊戲程式檔。有限標記未找到共用 `lobby-departure`、`story-scene`、本作色票 | 新增本作 `dispatch.css`：調度單、前後雙車廂、五格／十格數量圖、三站路徑；首頁優先數學。不是只替換顏色 |
| 字型組合 | Noto Sans TC 出現在交通學院、飛行／鐵道學校和暴風；Noto Serif TC 出現在暴風、灰燼、塔防 | 標準系統 fallback 字型，未下載或打包第三方字型；列明保留。新數學頁以清楚的無襯線教材文字為主，不借用戰鬥遊戲標題風格 |
| 按鈕／選單 | 共用瀏覽器標準元素，無同 bytes 的遊戲 UI | `child-targets.css` 統一至少 60px；新頁使用直角調度按鈕和逐人操作，橫屏獨立配置。保留舊玩法可達性測試並提高斷言 |
| `assets/icon.svg`、iOS AppIcon、Android mipmap、既有圖像 | 已掃描範圍未找到相同 bytes | 沿用本作已有列車圖示，不改成別款圖示；不是 App Store 全市場相似度鑑定 |
| 原生載入畫面 | 結構與交通學院相同，但 Splash PNG bytes 未發現完全重複 | 本輪改原生啟動版型以顯示數學定位；既有 raster 檔保留，沒有假稱重新繪製 |
| `src/celebration.js`、音效與語音 | 本作無新增聲音檔；回饋採既有 Web Audio 與裝置語音。跨作音色聽感未做實機 A/B | 保留可關閉回饋，新調度不加入通用勝利音軌。無新聲音授權需求；音色獨立性的實機聽測列缺件 |
| 文案 | 原有英文裝飾標題及首頁英文小標 | 已換成「列車觀察筆記」「我的學習足跡」「數學旅程完成」「動手拆合，數學上車」。runtime 掃描無 Lorem／TODO／Sample／敬請期待或公開除錯面板；模型代號、CC 授權等專有名詞保留 |
| Capacitor／原生 host | 交通學院也使用 Capacitor，其他作品另有 Godot／Unity 等建置來源 | 共用引擎與套件不是本作獨創技術，列明保留；不以框架不同作唯一區隔理由 |
| `games/*/{privacy,support}.html` | repo 既有多遊戲支援 URL 資料，不是可玩的其他遊戲 | 為既有公開支援連結契約保留原檔及 Web build 測試；主遊戲無跨作入口，不把這些頁面當內容差異證據。原生打包另排除此支援站目錄 |
| `docs/store/`、`docs/evidence/` | 本輪商店草稿／測試證據 | 建置排除，新增測試驗證不混入遊戲 payload；不讓審查草稿成為兒童內容 |

## 美術缺件

PREPARED：`assets-r3.json`。目前提供的產圖工具不能指定並確認 `gpt-image-2` model slug，所以本輪無新增 raster 原畫、沒有宣稱模型名稱，也沒有用程序化方塊代替角色／場景。座位圓點是數學數量圖，原生標題及按鈕是文字 UI。若要全面換原畫，仍需授權與可稽核的指定模型產物；既有素材的歷史模型來源沿用 manifest，不能倒填為 gpt-image-2。
