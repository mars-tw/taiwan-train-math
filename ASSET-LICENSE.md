# 教材與圖片授權

## 原創教材與 31 張 AI 情境插圖

`data/` 的原創編寫教材、`docs/` 的原創文字與 31 張列於 [assets/manifest.json](assets/manifest.json) 的 AI 情境插圖，在專案權利人可授權的範圍內，以 [Creative Commons 姓名標示 4.0 國際（CC BY 4.0）](https://creativecommons.org/licenses/by/4.0/deed.zh-hant) 提供。署名：**mars-tw／小小列車長**；AI 圖片生成工具：OpenAI ImageGen。此範圍不包含第三方實車照片、引用圖說及營運單位素材，也不影響事實本身及適用法律。

再散布或改作這些原創素材時，請保留專案連結、授權連結，並註明修改。範例：

> AI 情境插圖與原創教材：mars-tw「小小列車長」，CC BY 4.0；圖片由 OpenAI ImageGen 生成，已調整檔案尺寸。

AI 圖像為電影風情境插圖。星光高鐵與山海故事背景是想像素材，部分車型使用家族示意。原始生成提示、檔案與產出日期均保留於素材清單；舊旅程使用的 `image` 圖檔也保留。

## 第三方實車照片

目前有 58 張來源與授權完整的實車照片，另有 1 個待補條目。每張照片保留原作者與原授權，包括不同版本的 CC BY、CC BY-SA、CC0、Public domain 或政府網站資料開放宣告。請依該照片的原授權條款使用，保留署名、來源、授權連結及適用的修改說明。

[完整逐張授權表、來源與 SHA-256](docs/train-photo-credits.md) 由三份 `data/train-photos-*.json` 產生。第三方照片沒有改授權為 mars-tw 的 CC BY 4.0；內裝、尚未營運及待補狀態也分開標示。未確認授權的候選來源不當作可散布照片。

## 標誌、程式碼與裝置語音

官方標誌、商標、車型名稱與品牌權利歸各原權利人，這份素材授權不授予第三方商標權，也不代表營運單位背書。程式碼（含介面 SVG 與程式生成的數學示意圖）採根目錄 [Apache-2.0](LICENSE) 授權。裝置語音由使用者的瀏覽器與作業系統提供，不隨本專案散布錄音。

## 重建授權文件

執行 `node scripts/photo-credits.mjs` 可依最新照片清單重建本文件與逐張授權表；`node scripts/photo-credits.mjs --check` 只檢查是否一致，不改檔案。
