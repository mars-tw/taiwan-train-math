import sharp from "sharp";
import { readFile, writeFile, mkdir, readdir } from "node:fs/promises";
import { join } from "node:path";
const svg = await readFile("assets/icon.svg", "utf8");
const foreground = svg.replace(/<rect width="128" height="128"[^>]+\/>/, "");
const densities = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };
for (const [density, scale] of Object.entries(densities)) {
  const directory = `android/app/src/main/res/mipmap-${density}`;
  await mkdir(directory, { recursive: true });
  const icon = await sharp(Buffer.from(svg)).resize(Math.round(48 * scale), Math.round(48 * scale)).flatten({ background: "#152d32" }).png().toBuffer();
  await writeFile(join(directory, "ic_launcher.png"), icon);
  await writeFile(join(directory, "ic_launcher_round.png"), icon);
  const padding = Math.round(14 * scale);
  await sharp(Buffer.from(foreground)).resize(Math.round(80 * scale)).extend({ top: padding, bottom: padding, left: padding, right: padding, background: { r: 0, g: 0, b: 0, alpha: 0 } }).png().toFile(join(directory, "ic_launcher_foreground.png"));
}
await writeFile("android/app/src/main/res/drawable/ic_launcher_background.xml", '<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle"><solid android:color="#152d32"/></shape>');
await writeFile("android/app/src/main/res/values/ic_launcher_background.xml", '<resources><color name="ic_launcher_background">#152d32</color></resources>');
const appIconDir = "ios/App/App/Assets.xcassets/AppIcon.appiconset";
await mkdir(appIconDir, { recursive: true });
await sharp(Buffer.from(svg)).resize(1024, 1024).flatten({ background: "#152d32" }).png().toFile(join(appIconDir, "AppIcon-1024.png"));
await writeFile(join(appIconDir, "Contents.json"), JSON.stringify({ images: [{ filename: "AppIcon-1024.png", idiom: "universal", platform: "ios", size: "1024x1024" }], info: { author: "xcode", version: 1 } }, null, 2));
await mkdir("store-listing/assets", { recursive: true });
await sharp(Buffer.from(svg)).resize(512, 512).flatten({ background: "#152d32" }).png().toFile("store-listing/assets/google-play-icon-512.png");
await sharp(Buffer.from(svg)).resize(1024, 1024).flatten({ background: "#152d32" }).png().toFile("store-listing/assets/app-store-icon-1024.png");
const logo = await sharp(Buffer.from(svg)).resize(420, 420).png().toBuffer();
const splash = await sharp({ create: { width: 2732, height: 2732, channels: 3, background: "#f8f6f0" } }).composite([{ input: logo, gravity: "centre" }]).png().toBuffer();
for (const file of ["splash-2732x2732.png", "splash-2732x2732-1.png", "splash-2732x2732-2.png"]) await writeFile(`ios/App/App/Assets.xcassets/Splash.imageset/${file}`, splash);
for (const entry of await readdir("android/app/src/main/res", { withFileTypes: true })) {
  if (!entry.isDirectory() || !entry.name.startsWith("drawable")) continue;
  const path = `android/app/src/main/res/${entry.name}/splash.png`;
  try {
    const { width, height } = await sharp(await readFile(path)).metadata();
    const scaled = await sharp(Buffer.from(svg)).resize(Math.round(Math.min(width, height) * 0.22)).png().toBuffer();
    await sharp({ create: { width, height, channels: 3, background: "#f8f6f0" } }).composite([{ input: scaled, gravity: "centre" }]).png().toFile(path);
  } catch (error) { if (error.code !== "ENOENT") throw error; }
}
console.log("已依既有火車向量標誌產生 Android／Apple App 圖示。");
