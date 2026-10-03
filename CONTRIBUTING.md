# 一起把火車樂園做好

使用 Node.js 20 以上：`npm test`、`npm run build`、`npm run dev`。主程式沒有 npm 相依套件，不需要安裝套件。請先回報問題或提交小範圍 Pull Request。

新增列車：編輯 `data/trains.json`，提供唯一 `id`、繁體名稱、型號、分類、`modelKind`、介紹、圖片、示意種類與官方 `sources`。`type` 是型號、`fleet` 是車號系列、`name` 是服務或觀光名稱。未營運列車必須加 `status: future` 與清楚說明。圖片共用時使用 `imageKind: family`，不可假稱精確實車圖。補入 `docs/catalogue-coverage.md`，核對營運狀態，執行資料測試。

新增玩法：調整 `src/engine.js` 與 `src/app.js`。3–4 歲以 1–5 數量、兩個選項及三節排序為主；不要增加限時、扣分、付費、兒童註冊或追蹤。請測試錯答、提示、重試與完整旅程。

新增素材：確認可以公開再散布，記入 `assets/manifest.json`，提供來源、作者、授權、提示與修改資訊。維持明亮、真實電影風與安全鐵道情境。不要提交沒有授權的官方照片、商標、配音、秘密金鑰或個人資料。

請在桌面、390px 手機直式、鍵盤操作與減少動畫模式檢查。真實親子試玩請記錄匿名觀察，不上傳兒童影像或姓名。
