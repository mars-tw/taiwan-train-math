import { createServer } from "node:http";
import { readFile, realpath, stat } from "node:fs/promises";
import { networkInterfaces } from "node:os";
import { resolve, relative, extname, isAbsolute, sep } from "node:path";
import { fileURLToPath } from "node:url";

const publicDirectories = new Set(["src", "data", "assets", "docs", "licenses"]);
const publicFiles = new Set(["index.html", "privacy.html", "support.html", "manifest.webmanifest", "LICENSE", "NOTICE", "ASSET-LICENSE.md", "PRIVACY.md"]);
const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8",
  ".svg": "image/svg+xml; charset=utf-8",
  ".png": "image/png",
  ".webp": "image/webp",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".mp3": "audio/mpeg",
  ".wav": "audio/wav",
  ".ogg": "audio/ogg",
  ".mp4": "video/mp4",
  ".webm": "video/webm",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".md": "text/plain; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
};

function privateIPv4(address) {
  const parts = address.split(".").map(Number);
  return parts.length === 4 && parts.every((part) => Number.isInteger(part) && part >= 0 && part <= 255) &&
    (parts[0] === 10 || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) ||
      (parts[0] === 192 && parts[1] === 168));
}
export function lanAddresses(interfaces = networkInterfaces()) {
  const excluded = /tailscale|virtual|vmware|vethernet|hyper-v|docker|wsl|loopback|utun|(?:^|\W)(?:tun|tap)\d*|vpn|hamachi|zerotier|wireguard|container/i;
  const found = [], seen = new Set();
  for (const [name, entries] of Object.entries(interfaces)) {
    if (excluded.test(name)) continue;
    for (const entry of entries || []) {
      if ((entry.family !== "IPv4" && entry.family !== 4) || entry.internal ||
        !privateIPv4(entry.address) || seen.has(entry.address)) continue;
      found.push({ name, address: entry.address });
      seen.add(entry.address);
    }
  }
  return found;
}
export function previewOptions(args = process.argv.slice(2), env = process.env) {
  const portAt = args.indexOf("--port");
  const inline = args.find((arg) => arg.startsWith("--port="));
  const value = portAt >= 0 ? args[portAt + 1] : inline?.slice(7) ?? env.PORT ?? "4173";
  if (!/^\d+$/.test(String(value)) || Number(value) > 65535)
    throw new Error("連接埠請填 0–65535 的整數，例如 --port 4186。");
  return {
    root: resolve(args.includes("--dist") ? "dist" : "."),
    port: Number(value),
    host: args.includes("--lan") ? "0.0.0.0" : "127.0.0.1",
    lan: args.includes("--lan"),
  };
}
function publicPath(path) {
  const parts = path.split("/");
  if (parts.some((part) => !part || part.startsWith("."))) return false;
  return publicFiles.has(path) ||
    (parts.length > 1 && publicDirectories.has(parts[0]) && Boolean(mime[extname(path).toLowerCase()]));
}
function inside(root, file) {
  const path = relative(root, file);
  return path && !path.startsWith(".." + sep) && path !== ".." && !isAbsolute(path);
}
function sendText(req, res, status, message, extra = {}) {
  res.writeHead(status, {
    "Content-Type": "text/plain; charset=utf-8",
    "Content-Length": Buffer.byteLength(message),
    ...extra,
  });
  res.end(req.method === "HEAD" ? undefined : message);
}
export async function createPreviewServer({ root = resolve("."), lan = false } = {}) {
  const directory = await realpath(root);
  return createServer(async (req, res) => {
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("X-Content-Type-Options", "nosniff");
    if (req.method !== "GET" && req.method !== "HEAD") {
      sendText(req, res, 405, "只提供 GET 與 HEAD 預覽。", { Allow: "GET, HEAD" });
      return;
    }
    const peer = req.socket.remoteAddress?.replace(/^::ffff:/, "") || "";
    if (lan && !privateIPv4(peer) && peer !== "127.0.0.1" && peer !== "::1") {
      sendText(req, res, 403, "預覽只提供本機與家庭區域網路使用。");
      return;
    }
    try {
      // Inspect the raw path before URL normalization can erase ../ segments.
      let path;
      try { path = decodeURIComponent((req.url || "").split(/[?#]/, 1)[0]); }
      catch { sendText(req, res, 400, "網址格式不正確。"); return; }
      if (!path.startsWith("/") || /[\\:%\u0000-\u001f\u007f]/.test(path)) {
        sendText(req, res, 403, "這個路徑不提供預覽。");
        return;
      }
      if (path.endsWith("/")) path += "index.html";
      const requested = path.slice(1);
      if (!publicPath(requested)) {
        sendText(req, res, 403, "這個檔案不提供預覽。");
        return;
      }
      const candidate = resolve(directory, requested);
      if (!inside(directory, candidate)) {
        sendText(req, res, 403, "這個路徑不提供預覽。");
        return;
      }
      // A public-directory link must not point outside the root or at a private file.
      const file = await realpath(candidate);
      const canonical = relative(directory, file).split(sep).join("/");
      if (!inside(directory, file) || !publicPath(canonical)) {
        sendText(req, res, 403, "這個檔案不提供預覽。");
        return;
      }
      const info = await stat(file);
      if (!info.isFile()) { sendText(req, res, 404, "找不到檔案。"); return; }
      const body = req.method === "HEAD" ? undefined : await readFile(file);
      res.writeHead(200, {
        "Content-Type": mime[extname(file).toLowerCase()] || "text/plain; charset=utf-8",
        "Content-Length": body?.length ?? info.size,
      });
      res.end(body);
    } catch {
      sendText(req, res, 404, "找不到檔案。");
    }
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const options = previewOptions();
    const server = await createPreviewServer(options);
    server.on("error", (error) => {
      console.error(`預覽無法啟動：${error.code || error.message}`);
      process.exitCode = 1;
    });
    server.listen(options.port, options.host, () => {
      const port = server.address().port;
      console.log(`遊戲預覽：http://127.0.0.1:${port}`);
      if (!options.lan) return;
      const addresses = lanAddresses();
      for (const entry of addresses)
        console.log(`同 Wi-Fi 手機／平板：http://${entry.address}:${port}（${entry.name}）`);
      if (!addresses.length) console.log("尚未找到可顯示的家庭網路 IPv4 位址。");
      console.log("請保持這個視窗開著。只供同一家庭網路試玩，未建立公開連結。若手機連不上，請先檢查 Wi-Fi 與防火牆。");
    });
  } catch (error) {
    console.error(`預覽無法啟動：${error.message}`);
    process.exitCode = 1;
  }
}
