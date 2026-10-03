# 小小列車長｜台灣火車數學樂園

給 **3–8 歲**小小鐵道迷的免費繁體中文網頁遊戲。陪星光高鐵送信到海邊，點開旅途小驚喜，再選喜歡的真實列車，練習數數、簡單加減、排序、規律、裝箱、記憶、時鐘、空間方向、分享與尋寶。

[直接遊玩](https://mars-tw.github.io/taiwan-train-math/) · [公開程式庫](https://github.com/mars-tw/taiwan-train-math)

## 可以玩什麼

- **3–4 歲**：1–5 數量與點點配對、列車名稱配對、三節車廂排序、AB 圖形規律、1–5 箱裝貨、兩對記憶翻卡；每趟三站。
- **5–6 歲**：0–10 數數、10 以內上車下車加減、列車配對、五節排序、數量比較、AAB／ABC 規律、10 箱內裝貨、三對翻卡及整點時鐘。
- **7–8 歲**：0–20 數數與加減、列車型號配對、排序與比較、跳數規律、20 箱內裝貨、四對翻卡及整點半點。跨十加減由家長開啟。
- **星光高鐵故事**：獨立透明列車沿山海軌道緩緩向下開，四段情節，可暫停、重播、手動換段和聽故事。點小鳥、燈塔與信封，直接進入故事任務。
- **三個新冒險**：旋轉軌道接通路線；把點心公平分給朋友，可隨時搬回；在風景裡找星星、葉子與貝殼。三種都依年齡調整，無時間壓力。
- 自由選車、山海地圖、暖陽／暮色、圖鑑搜尋、十二種單項練習與隨機驚喜旅程、本機鐵道護照、中文裝置語音、柔和音效與減少動畫。
- 完成旅程可拆開紀念信封，收藏十二款旅途小禮物；不付費、不鎖遊戲、不限時收集。
- 無計時扣分。答錯可以再試，提示能協助完成。所有列車直接開放。

收錄 **59 個車型、車號系列與列車名稱條目**：台鐵主要動力車型、高鐵 700T、阿里山林鐵、觀光與糖鐵列車，以及日本 E5、N700S 子彈列車、L0 磁浮試驗列車。N700ST 另標為未來規劃。[完整收錄範圍](docs/catalogue-coverage.md)。

**31 張電影風圖片為 AI 情境插圖。** 星光高鐵是想像故事列車，與圖鑑的台灣高鐵 700T 分開。部分車型共用家族示意，不能以圖中細節辨識實車。車型、車號與服務名稱分開標示，附官方資料來源。這不是逐輛現役車籍或營運時刻表，也不宣稱收齊台灣所有工程車、貨車與保存車。

## 在自己的電腦執行

需要 Node.js 20 以上。無執行期套件依賴，無須 `npm install`。

```sh
git clone https://github.com/mars-tw/taiwan-train-math.git
cd taiwan-train-math
npm run dev
```

開啟 **http://127.0.0.1:4173**。請用伺服器開啟，不要直接雙擊 index.html；瀏覽器模組與 JSON 載入需要 HTTP。

```sh
npm test
npm run build
node scripts/serve.mjs --dist
```

`dist/` 可放到一般靜態主機。手機瀏覽公開網址即可，不需要安裝 App。首次載入需要網路，尚未提供離線快取。

## GitHub Pages

本儲存庫已啟用 GitHub Pages，公開網址可以直接遊玩。自行 fork 時，管理者在 **Settings → Pages → Build and deployment → Source** 選 **GitHub Actions**。推送 main 會執行測試、建立靜態檔案並部署；也可在 Actions 的 **Test and publish game** 手動執行。

首次啟用是 GitHub 儲存庫的主機設定。若未啟用，公開程式庫仍可下載與本機遊玩，但 Pages 網址會顯示 404。

## 專案結構

- `src/app.js`：畫面、遊戲互動、語音與本機護照。
- `src/home.js`／`src/immersive.css`：可探索首頁及新玩法美術。
- `src/activities.js`：規律、裝箱、翻卡及時鐘的可操作教材畫面。
- `src/story.js`／`src/story-model.js`／`src/story.css`：四段故事、實際列車動畫與動畫生命週期。
- `src/adventure.js`／`src/adventure-ui.js`：鋪軌、點心分享、尋寶及旅途禮物。
- `src/engine.js`：分齡題目生成、答案檢查、儲存容錯。
- `data/trains.json`：車型、介紹、分類與來源；`questions.json` 為初始題目範例，實際遊戲由引擎生成。
- `assets/images/`：電影風 WebP 圖片；`assets/manifest.json`：生成提示與授權紀錄。
- `docs/`：[遊戲規劃](docs/game-plan.md)、[素材設計](docs/assets.md)、[首頁美術規劃](docs/art-direction-v2.md)、[故事與新冒險規劃](docs/story-adventure-v3.md)、[工作清單](docs/tasks.md)、[來源與授權](docs/sources-and-licenses.md)、[驗證紀錄](docs/validation.md)。
- `tests/`：題目與資料驗證。

## 授權與隱私

沿用此儲存庫建立時選擇的 **Apache-2.0** 程式授權；編寫教材與可授權圖像採 **CC BY 4.0**。請見 [LICENSE](LICENSE)、[素材授權](ASSET-LICENSE.md)、[NOTICE](NOTICE)、[隱私說明](PRIVACY.md) 與 [貢獻指南](CONTRIBUTING.md)。

非官方教育專案，不代表台鐵、高鐵、林鐵或海外營運單位。語音預設關閉；裝置是否使用遠端朗讀依瀏覽器供應商而定。遊戲不設帳號、廣告或追蹤程式，集章與禮物僅儲存在本機。

目前版本 1.2.0，保留 v1 本機護照與偏好。真實親子試玩與 Safari／實體行動裝置驗證列於待辦，歡迎回報問題。
