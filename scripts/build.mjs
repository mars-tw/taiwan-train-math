import { cp, mkdir } from "node:fs/promises";
await mkdir("dist", { recursive: true });
for (const path of [
  "index.html",
  "manifest.webmanifest",
  "src",
  "data",
  "assets",
  "docs",
  "LICENSE",
  "NOTICE",
  "ASSET-LICENSE.md",
  "PRIVACY.md",
])
  await cp(path, `dist/${path}`, { recursive: true });
console.log("已建立 dist：可部署於 GitHub Pages 或一般靜態主機。");
