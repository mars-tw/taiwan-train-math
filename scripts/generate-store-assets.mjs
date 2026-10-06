import sharp from "sharp";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";

// Run: node scripts/generate-store-assets.mjs
// Other hosts: add --font-file /path/to/CJK-font.ttf and --font-family "Noto Sans CJK TC".
// No downloads. Reuses the existing imaginary landscape (CC BY 4.0, mars-tw)
// and vector app icon; it does not depict a newly generated real train.
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = join(root, "store-listing/assets/google-play-feature-1024x500.png");
const options = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  const key = process.argv[index];
  if (!["--font-file", "--font-family"].includes(key) || !process.argv[index + 1]) {
    throw new Error("Supported options: --font-file PATH --font-family NAME");
  }
  options.set(key, process.argv[index + 1]);
}
const fontfile = options.get("--font-file") || "C:/Windows/Fonts/msjhbd.ttc";
const family = options.get("--font-family") || "Microsoft JhengHei";
try { await access(fontfile); }
catch { throw new Error("Provide an installed Traditional Chinese font with --font-file and --font-family. No font is downloaded or bundled."); }

const width = 1024;
const height = 500;
const title = "小小列車長";
const subtitle = "數學・台灣火車・山海故事";
const [landscape, icon] = await Promise.all([
  sharp(await readFile(join(root, "assets/images/story-coast-v3.webp")))
    .resize(width, height, { fit: "cover", position: "centre" }).png().toBuffer(),
  sharp(await readFile(join(root, "assets/icon.svg"))).resize(148, 148).png().toBuffer(),
]);
const veil = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="500">
  <defs><linearGradient id="shade"><stop offset="0" stop-color="#152d32" stop-opacity=".98"/>
    <stop offset=".43" stop-color="#152d32" stop-opacity=".91"/>
    <stop offset=".7" stop-color="#152d32" stop-opacity=".15"/>
    <stop offset="1" stop-color="#152d32" stop-opacity="0"/></linearGradient></defs>
  <rect width="1024" height="500" fill="url(#shade)"/>
</svg>`);
const textImage = (text, size, color) => sharp({
  text: {
    text: `<span foreground="${color}">${text}</span>`,
    font: `${family} Bold ${size}`, fontfile, dpi: 72, rgba: true,
  },
}).png().toBuffer({ resolveWithObject: true });
const [heading, caption] = await Promise.all([
  textImage(title, 76, "#fff9ed"), textImage(subtitle, 25, "#f7b366"),
]);
if (heading.info.width > 510 || caption.info.width > 510) {
  throw new Error("The selected font makes the text too wide for the landscape layout.");
}
const png = await sharp(landscape).composite([
  { input: veil, left: 0, top: 0 },
  { input: icon, left: 64, top: 65 },
  { input: heading.data, left: 64, top: 254 },
  { input: caption.data, left: 68, top: 358 },
]).flatten({ background: "#152d32" }).removeAlpha().png({ compressionLevel: 9 }).toBuffer();
const metadata = await sharp(png).metadata();
if (metadata.width !== width || metadata.height !== height || metadata.hasAlpha || metadata.channels !== 3) {
  throw new Error("Google Play feature graphic must be exactly 1024×500 RGB PNG with no alpha.");
}
await mkdir(dirname(output), { recursive: true });
await writeFile(output, png);
console.log(JSON.stringify({
  output, width: metadata.width, height: metadata.height, channels: metadata.channels,
  hasAlpha: metadata.hasAlpha, bytes: png.length,
  sha256: createHash("sha256").update(png).digest("hex"),
  title, subtitle, fontfile, family,
}, null, 2));
