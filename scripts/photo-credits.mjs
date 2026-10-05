import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCES = ["tra", "special", "tourism"].map(name => `data/train-photos-${name}.json`);
const LOCAL = /^assets\/images\/real-[a-z0-9-]+\.(?:jpg|png|webp)$/;
const url = value => /^https?:\/\//.test(String(value || ""));
const plain = value => String(value ?? "").replace(/<[^>]*>/g, "").replace(/&amp;/g, "&")
  .replace(/[\r\n\u200b-\u200f\ufeff]+/g, " ").replace(/\s+/g, " ").trim();
const cell = value => plain(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\|/g, "\\|");
const href = value => String(value).replace(/[\s()<>]/g, character => encodeURIComponent(character));
const link = (label, target) => target ? `[${cell(label)}](${href(target)})` : "—";
function manifestRows(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.photos)) return value.photos;
  throw new Error("Photo manifest must contain a photos array");
}
export function normalizePhotoRecord(row) {
  return {
    ...row,
    sourceUrl: row.sourceUrl || row.filePage || row.source || "",
    thumbnailUrl: row.thumbnailUrl || row.thumbnailURL || "",
    licenseUrl: row.licenseUrl || row.licenseURL || "",
    author: plain(row.author), licenseName: plain(row.licenseName),
    fileTitle: plain(row.fileTitle || row.title || ""),
  };
}
export function hasCompletePhotoCredit(row) {
  return row?.status === "verified" && LOCAL.test(row.path || "") && Boolean(plain(row.author))
    && Boolean(plain(row.licenseName)) && url(row.licenseUrl) && url(row.sourceUrl)
    && url(row.thumbnailUrl) && /^[a-f0-9]{64}$/.test(row.sha256 || "");
}
function creditProblem(row) {
  if (row.status !== "verified") return plain(row.reason) || "實車身分或再利用授權尚未確認。";
  const missing = ["path", "author", "licenseName", "licenseUrl", "sourceUrl", "thumbnailUrl", "sha256"]
    .filter(key => !row[key]);
  return `授權或來源資料不完整${missing.length ? `：${missing.join("、")}` : "，請確認圖檔路徑、網址及雜湊格式"}。`;
}
export function renderPhotoCreditDocuments({ catalogue, artwork, manifests }) {
  const byId = new Map();
  for (const manifest of manifests) for (const raw of manifestRows(manifest)) {
    const row = normalizePhotoRecord(raw);
    if (!row.id || byId.has(row.id)) throw new Error(`Missing or repeated photo id: ${row.id}`);
    byId.set(row.id, row);
  }
  const known = new Set(catalogue.trains.map(train => train.id));
  for (const id of byId.keys()) if (!known.has(id)) throw new Error(`Photo not in catalogue: ${id}`);
  const rows = catalogue.trains.map(train => {
    const record = byId.get(train.id) || { id: train.id, status: "pending", reason: "照片清單尚未建立。" };
    return { ...record, name: train.displayName || train.name,
      canonicalModel: record.canonicalModel || train.canonicalModel || train.displayModel || train.model,
      view: record.view || train.referencePhoto?.view || "unknown", future: train.status === "future" };
  });
  const verified = rows.filter(hasCompletePhotoCredit), pending = rows.filter(row => !hasCompletePhotoCredit(row));
  const date = plain(catalogue.reviewed || "未標示");
  const purpose = row => row.view === "interior" ? "內裝；不作外觀題"
    : row.future ? "抵台實車；尚未營運、不作遊戲題" : row.view === "exterior" ? "外觀" : "照片；視角待標示";
  const table = verified.map(row => `| \`${cell(row.id)}\` | ${cell(row.name)} | ${cell(purpose(row))} | ${link(row.path.split("/").at(-1), `../${row.path}`)} | ${cell(row.author)} | ${link(row.licenseName, row.licenseUrl)} | ${link("檔案頁", row.sourceUrl)} · ${link("原始縮圖", row.thumbnailUrl)} |`).join("\n");
  const hashes = verified.map(row => `| \`${cell(row.id)}\` | \`${row.sha256}\` |`).join("\n");
  const identities = verified.map(row => `| \`${cell(row.id)}\` | ${cell(row.canonicalModel)} | ${cell(row.modelEvidence || row.description)} |`).join("\n");
  const pendingTable = pending.map(row => `| \`${cell(row.id)}\` | ${cell(row.name)} | ${cell(creditProblem(row))} | ${url(row.sourceUrl) ? link("候選來源；授權未確認", row.sourceUrl) : "—"} |`).join("\n");
  const photoCredits = `# 實車照片來源與授權\n\n此檔由 \`node scripts/photo-credits.mjs\` 依三份照片清單產生。核對日期：${date}。\n\n共 ${rows.length} 個列車條目：${verified.length} 張已驗證、授權及來源欄位完整的實車照片，${pending.length} 個待補條目。照片沿用各原作者提供的授權；本專案的 CC BY 4.0 不重新授權這些第三方照片。\n\n## 逐張授權表\n\n表中連結保留檔案來源、實際下載縮圖及原授權。照片使用 Commons 官方縮圖；未另行 AI 生成或修圖。請依各列原授權履行署名、修改說明及適用的相同方式分享條件。\n\n| 條目 | 顯示名稱 | 照片用途 | 本機圖檔 | 原作者 | 原授權 | 原始來源 |\n| --- | --- | --- | --- | --- | --- | --- |\n${table}\n\n## 型號與車號核對\n\nDR1000 與 DRC1000 為同型命名，\`canonicalModel\` 同為 DR1000。兩張不同車號照片各自保留來源與授權，外觀遊戲只使用一個同型代表。內裝與尚未營運的列車照片供圖鑑對照。\n\n| 條目 | 統一身分 | 圖片核對證據 |\n| --- | --- | --- |\n${identities}\n\n## 圖檔完整性\n\nSHA-256 對應本機保存的縮圖原始位元組。重新下載或更換照片後，需重新核對來源、授權、型號與雜湊，再更新清單。\n\n| 條目 | SHA-256 |\n| --- | --- |\n${hashes}\n\n## 待補條目\n\n待補照片不宣稱已取得再利用授權，也不列入外觀照片遊戲。請取得可核對的原作者及公開授權，再加入實照圖檔。\n\n| 條目 | 顯示名稱 | 待補原因 | 候選來源 |\n| --- | --- | --- | --- |\n${pendingTable || "| — | — | 無待補條目 | — |"}\n\n## 清單與重建\n\n${SOURCES.map(file => `- ${link(file, `../${file}`)}`).join("\n")}\n\n重建：\`node scripts/photo-credits.mjs\`。只檢查文件是否一致：\`node scripts/photo-credits.mjs --check\`。本腳本不下載圖片、不變更列車或照片資料，也不改動原始圖片。\n`;
  const assetLicense = `# 教材與圖片授權\n\n## 原創教材與 ${artwork.images.length} 張 AI 情境插圖\n\n\`data/\` 的原創編寫教材、\`docs/\` 的原創文字與 ${artwork.images.length} 張列於 [assets/manifest.json](assets/manifest.json) 的 AI 情境插圖，在專案權利人可授權的範圍內，以 [Creative Commons 姓名標示 4.0 國際（CC BY 4.0）](https://creativecommons.org/licenses/by/4.0/deed.zh-hant) 提供。署名：**mars-tw／小小列車長**；AI 圖片生成工具：OpenAI ImageGen。此範圍不包含第三方實車照片、引用圖說及營運單位素材，也不影響事實本身及適用法律。\n\n再散布或改作這些原創素材時，請保留專案連結、授權連結，並註明修改。範例：\n\n> AI 情境插圖與原創教材：mars-tw「小小列車長」，CC BY 4.0；圖片由 OpenAI ImageGen 生成，已調整檔案尺寸。\n\nAI 圖像為電影風情境插圖。星光高鐵與山海故事背景是想像素材，部分車型使用家族示意。原始生成提示、檔案與產出日期均保留於素材清單；舊旅程使用的 \`image\` 圖檔也保留。\n\n## 第三方實車照片\n\n目前有 ${verified.length} 張來源與授權完整的實車照片，另有 ${pending.length} 個待補條目。每張照片保留原作者與原授權，包括不同版本的 CC BY、CC BY-SA、CC0、Public domain 或政府網站資料開放宣告。請依該照片的原授權條款使用，保留署名、來源、授權連結及適用的修改說明。\n\n[完整逐張授權表、來源與 SHA-256](docs/train-photo-credits.md) 由三份 \`data/train-photos-*.json\` 產生。第三方照片沒有改授權為 mars-tw 的 CC BY 4.0；內裝、尚未營運及待補狀態也分開標示。未確認授權的候選來源不當作可散布照片。\n\n## 標誌、程式碼與裝置語音\n\n官方標誌、商標、車型名稱與品牌權利歸各原權利人，這份素材授權不授予第三方商標權，也不代表營運單位背書。程式碼（含介面 SVG 與程式生成的數學示意圖）採根目錄 [Apache-2.0](LICENSE) 授權。裝置語音由使用者的瀏覽器與作業系統提供，不隨本專案散布錄音。\n\n## 重建授權文件\n\n執行 \`node scripts/photo-credits.mjs\` 可依最新照片清單重建本文件與逐張授權表；\`node scripts/photo-credits.mjs --check\` 只檢查是否一致，不改檔案。\n`;
  return { assetLicense, photoCredits, verified: verified.length, pending: pending.length, rows };
}
export async function photoCreditDocuments(root = ROOT) {
  const readJson = async path => JSON.parse(await readFile(resolve(root, path), "utf8"));
  const [catalogue, artwork, ...manifests] = await Promise.all(["data/trains.json", "assets/manifest.json", ...SOURCES].map(readJson));
  const result = renderPhotoCreditDocuments({ catalogue, artwork, manifests });
  for (const row of result.rows.filter(hasCompletePhotoCredit)) {
    if (!existsSync(resolve(root, row.path))) throw new Error(`Missing photo: ${row.path}`);
    const actual = createHash("sha256").update(await readFile(resolve(root, row.path))).digest("hex");
    if (actual !== row.sha256) throw new Error(`Photo hash mismatch: ${row.id}`);
  }
  return result;
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = await photoCreditDocuments();
  const files = [["ASSET-LICENSE.md", result.assetLicense], ["docs/train-photo-credits.md", result.photoCredits]];
  if (process.argv.includes("--check")) {
    for (const [path, content] of files)
      if (await readFile(resolve(ROOT, path), "utf8") !== content) throw new Error(`Run node scripts/photo-credits.mjs to update ${path}`);
  } else {
    for (const [path, content] of files) {
      await mkdir(dirname(resolve(ROOT, path)), { recursive: true });
      await writeFile(resolve(ROOT, path), content, "utf8");
    }
  }
  console.log(`照片授權文件${process.argv.includes("--check") ? "檢查通過" : "已更新"}：${result.verified} 張已驗證、${result.pending} 個待補。`);
}
