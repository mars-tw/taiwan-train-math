import { copyFile, lstat, mkdir, readFile, readdir, realpath, rm } from "node:fs/promises";
import { basename, dirname, join, posix, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const publicEntries = [
  "index.html", "privacy.html", "support.html", "manifest.webmanifest", "src", "data", "assets", "docs",
  "LICENSE", "NOTICE", "ASSET-LICENSE.md", "PRIVACY.md",
];

async function publicFiles(root) {
  const files = [];
  async function visit(path) {
    const info = await lstat(join(root, path));
    if (info.isSymbolicLink()) throw new Error(`公開素材不能是符號連結或目錄連結：${path}`);
    if (info.isFile()) { files.push(path); return; }
    if (!info.isDirectory()) throw new Error(`公開素材必須是一般檔案或目錄：${path}`);
    for (const name of (await readdir(join(root, path))).sort()) {
      if (!name.startsWith(".")) await visit(`${path}/${name}`);
    }
  }
  for (const entry of publicEntries) await visit(entry);
  return files;
}

function checkReference(files, owner, reference, { rootRelative = false, directory = false } = {}) {
  const value = reference.trim().replaceAll("&amp;", "&");
  if (!value || value.startsWith("#") || /^(?:[a-z][\w+.-]*:|\/\/)/i.test(value)) return;
  if (value.startsWith("/") || value.includes("\\"))
    throw new Error(`請使用可部署於專案子目錄的相對路徑：${owner} → ${reference}`);
  const rawPath = value.split(/[?#]/, 1)[0];
  if (!rawPath) return;
  let decoded;
  try { decoded = decodeURIComponent(rawPath); }
  catch { throw new Error(`網址編碼不正確：${owner} → ${reference}`); }
  if (decoded.includes("\\") || decoded.startsWith("/"))
    throw new Error(`公開素材路徑不正確：${owner} → ${reference}`);
  let path = posix.normalize(posix.join(rootRelative ? "." : posix.dirname(owner), decoded));
  if (path === ".." || path.startsWith("../"))
    throw new Error(`公開素材路徑超出專案：${owner} → ${reference}`);
  if (directory || path === "." || decoded.endsWith("/")) path = posix.join(path, "index.html");
  if (!files.has(path)) throw new Error(`找不到公開素材（請確認路徑及大小寫）：${owner} → ${reference}`);
}

async function checkReferences(root, paths) {
  const files = new Set(paths);
  for (const owner of paths) {
    if (!/\.(?:html|js|css|json|webmanifest)$/.test(owner)) continue;
    const source = await readFile(join(root, owner), "utf8");
    if (owner.endsWith(".html")) {
      for (const match of source.matchAll(/\b(?:src|href)\s*=\s*(["'])(.*?)\1/gis))
        checkReference(files, owner, match[2]);
    } else if (owner.endsWith(".js")) {
      for (const match of source.matchAll(/\b(?:import|export)\s+(?:[\w*{},\s]+?\s+from\s+)?(["'])([^"'\r\n]+)\1/g)) {
        if (!match[2].startsWith(".")) throw new Error(`瀏覽器模組需使用相對路徑：${owner} → ${match[2]}`);
        checkReference(files, owner, match[2]);
      }
      for (const match of source.matchAll(/\bimport\s*\(\s*(["'])([^"'\r\n]+)\1\s*\)/g))
        checkReference(files, owner, match[2]);
      // Runtime game assets are relative to the document, not the module file.
      for (const match of source.matchAll(/(["'])(?:\.\/)?((?:assets|data|docs)\/[^"'\r\n]+)\1/g))
        checkReference(files, owner, match[2], { rootRelative: true });
    } else if (owner.endsWith(".css")) {
      for (const match of source.matchAll(/\burl\(\s*(?:(["'])(.*?)\1|([^\s)]+))\s*\)/gis))
        checkReference(files, owner, match[2] ?? match[3]);
    } else {
      const document = JSON.parse(source);
      if (owner === "manifest.webmanifest") {
        for (const icon of document.icons || []) checkReference(files, owner, icon.src);
        checkReference(files, owner, document.start_url || "./");
        checkReference(files, owner, document.scope || "./", { directory: true });
      }
      const visit = (value) => {
        if (typeof value === "string" && /^(?:assets|src|data|docs)\/[^\s]+$/.test(value))
          checkReference(files, owner, value, { rootRelative: true });
        else if (Array.isArray(value)) value.forEach(visit);
        else if (value && typeof value === "object") Object.values(value).forEach(visit);
      };
      visit(document);
    }
  }
}

export async function buildSite(projectRoot = process.cwd()) {
  const root = await realpath(projectRoot);
  const output = resolve(root, "dist");
  // The only recursive deletion target is this project's literal dist directory.
  if (dirname(output) !== root || basename(output) !== "dist") throw new Error("建置目錄不正確。");
  let outputInfo;
  try { outputInfo = await lstat(output); }
  catch (error) { if (error.code !== "ENOENT") throw error; }
  if (outputInfo?.isSymbolicLink() || (outputInfo && !outputInfo.isDirectory()))
    throw new Error("dist 必須是專案內的一般目錄，不能是檔案或目錄連結。");
  // Complete the preflight before replacing a previously successful build.
  const files = await publicFiles(root);
  await checkReferences(root, files);
  await rm(output, { recursive: true, force: true });
  await mkdir(output);
  for (const path of files) {
    const destination = join(output, path);
    await mkdir(dirname(destination), { recursive: true });
    await copyFile(join(root, path), destination);
  }
  return { output, files: files.length };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const result = await buildSite();
    console.log(`已建立 dist（${result.files} 個檔案）：可部署於 GitHub Pages 或一般靜態主機。`);
  } catch (error) {
    console.error(`建置失敗：${error.message}`);
    process.exitCode = 1;
  }
}
