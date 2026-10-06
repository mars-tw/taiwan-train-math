import { buildSite } from "./build.mjs";
import { build } from "esbuild";
import { readFile, writeFile, mkdir, cp, rm, readdir, lstat } from "node:fs/promises";
import { resolve, join, dirname, basename } from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "dist-native");
if (dirname(out) !== root || basename(out) !== "dist-native") throw new Error("Invalid native output");
try { if ((await lstat(out)).isSymbolicLink()) throw new Error("Native output must not be linked"); } catch (error) { if (error.code !== "ENOENT") throw error; }
await buildSite(root);
await rm(out, { recursive: true, force: true });
await cp(join(root, "dist"), out, { recursive: true, dereference: false });
await build({ entryPoints: [join(root, "native/host-entry.js")], outfile: join(out, "native-host.js"), bundle: true, format: "iife", target: "es2020", platform: "browser", minify: true });
await cp(join(root, "native/native-ui.css"), join(out, "native-ui.css"));
const documents = {};
for (const path of ["PRIVACY.md", "LICENSE", "NOTICE", "ASSET-LICENSE.md", "docs/train-photo-credits.md", "docs/sources-and-licenses.md", "docs/catalogue-coverage.md", "docs/art-direction-v2.md", "docs/story-adventure-v3.md"]) documents[path] = await readFile(join(root, path), "utf8");
documents["privacy.html"] = documents["PRIVACY.md"];
documents["support.html"] = await readFile(join(root, "docs/native-support.md"), "utf8");
await writeFile(join(out, "native-documents.js"), `window.TrainMathNativeDocuments=${JSON.stringify(documents).replaceAll("<", "\\u003c")};\n`);
const html = (await readFile(join(out, "index.html"), "utf8")).replace("</head>", '<link rel="stylesheet" href="native-ui.css"><script src="native-documents.js"></script><script src="native-host.js"></script></head>');
await writeFile(join(out, "index.html"), html);
const config = JSON.parse(await readFile(join(root, "capacitor.config.json"), "utf8"));
if (config.webDir !== "dist-native" || config.server?.url || config.server?.cleartext) throw new Error("Native app must use a local package");
const files = [];
async function collect(directory, prefix = "") {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) throw new Error("Linked native asset");
    const path = `${prefix}${entry.name}`;
    if (entry.isDirectory()) await collect(join(directory, entry.name), `${path}/`);
    else { const bytes = await readFile(join(directory, entry.name)); files.push({ path, bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") }); }
  }
}
await collect(out);
await mkdir(join(root, "output/native"), { recursive: true });
const pkg = JSON.parse(await readFile(join(root, "package.json"), "utf8"));
const report = { appId: config.appId, appName: config.appName, webSourceVersion: pkg.version, webDir: config.webDir, remoteServer: false, files: files.sort((a,b) => a.path.localeCompare(b.path)), bytes: files.reduce((total, file) => total + file.bytes, 0) };
await writeFile(join(root, "output/native/bundle-manifest.json"), JSON.stringify(report, null, 2));
console.log(`原生離線素材已打包：${files.length} 個檔案，${report.bytes} bytes。`);
