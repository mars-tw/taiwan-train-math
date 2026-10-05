import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { request } from "node:http";
import { once } from "node:events";
import { mkdtemp, mkdir, writeFile, symlink, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { createPreviewServer, previewOptions, lanAddresses } from "../scripts/serve.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const script = fileURLToPath(new URL("../scripts/serve.mjs", import.meta.url));
function get(port, path, method = "GET", hostname = "127.0.0.1") {
  return new Promise((resolveResponse, reject) => {
    const req = request({ hostname, port, path, method, agent: false }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => resolveResponse({
        status: response.statusCode, headers: response.headers, body: Buffer.concat(chunks),
      }));
    });
    req.on("error", reject);
    req.setTimeout(3000, () => req.destroy(new Error("Preview request timed out")));
    req.end();
  });
}
async function start(t, args = []) {
  const child = spawn(process.execPath, [script, "--port", "0", ...args], {
    cwd: root, stdio: ["ignore", "pipe", "pipe"],
  });
  const exited = once(child, "exit");
  const stop = async () => { if (child.exitCode === null && child.signalCode === null) child.kill(); await exited; };
  t.after(stop);
  let output = "", errors = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => { errors += chunk; });
  const port = await new Promise((ready, reject) => {
    const timer = setTimeout(() => reject(new Error(`Preview did not start: ${errors}`)), 5000);
    child.stdout.on("data", (chunk) => {
      output += chunk;
      const match = output.match(/遊戲預覽：http:\/\/127\.0\.0\.1:(\d+)/);
      if (match && (!args.includes("--lan") || output.includes("未建立公開連結"))) {
        clearTimeout(timer);
        ready(Number(match[1]));
      }
    });
    child.once("error", (error) => { clearTimeout(timer); reject(error); });
    child.once("exit", () => { clearTimeout(timer); reject(new Error(`Preview exited early: ${errors}`)); });
  });
  return { port, output, stop };
}

test("LAN mode is explicit and only useful private physical IPv4 addresses are suggested", () => {
  assert.equal(previewOptions([], {}).host, "127.0.0.1");
  assert.equal(previewOptions(["--lan", "--port", "4186"], {}).host, "0.0.0.0");
  assert.equal(previewOptions(["--port=4186"], {}).port, 4186);
  assert.equal(previewOptions([], { PORT: "4185" }).port, 4185);
  for (const port of ["-1", "65536", "NaN", "1.5", ""]) assert.throws(() => previewOptions(["--port", port], {}));
  assert.throws(() => previewOptions(["--port"], {}));
  const address = (ip, extra = {}) => ({ family: "IPv4", internal: false, address: ip, ...extra });
  assert.deepEqual(lanAddresses({
    "Wi-Fi": [address("192.168.0.144"), { family: "IPv6", address: "fe80::1", internal: false }],
    Ethernet: [address("10.0.0.4"), address("192.168.0.144")],
    Tailscale: [address("100.93.11.92")],
    "vEthernet (WSL)": [address("172.18.0.1")],
    "VMware Network Adapter": [address("192.168.56.1")],
    tun0: [address("10.8.0.1")],
    Loopback: [address("127.0.0.1", { internal: true })],
    Public: [address("203.0.113.4")],
  }), [{ name: "Wi-Fi", address: "192.168.0.144" }, { name: "Ethernet", address: "10.0.0.4" }]);
});

test("the actual CLI serves game assets and HEAD without exposing repository files", async (t) => {
  const running = await start(t);
  for (const [path, type] of [
    ["/", "text/html"], ["/index.html", "text/html"],
    ["/assets/icon.svg", "image/svg+xml"], ["/manifest.webmanifest", "application/manifest+json"],
    ["/src/app.js?v=mobile-test", "text/javascript"], ["/src/styles.css", "text/css"],
    ["/data/trains.json", "application/json"], ["/docs/sources-and-licenses.md", "text/plain"],
    ["/LICENSE", "text/plain"], ["/NOTICE", "text/plain"], ["/ASSET-LICENSE.md", "text/plain"], ["/PRIVACY.md", "text/plain"],
  ]) {
    const response = await get(running.port, path);
    assert.equal(response.status, 200, path);
    assert.ok(response.headers["content-type"].startsWith(type), path);
    assert.equal(response.headers["cache-control"], "no-cache");
    assert.equal(response.headers["x-content-type-options"], "nosniff");
    assert.equal(Number(response.headers["content-length"]), response.body.length);
    assert.ok(response.body.length > 0);
    const head = await get(running.port, path, "HEAD");
    assert.equal(head.status, 200, path);
    assert.equal(head.body.length, 0);
    assert.equal(head.headers["content-length"], response.headers["content-length"]);
    assert.equal(head.headers["content-type"], response.headers["content-type"]);
  }
  for (const path of [
    "/README.md", "/package.json", "/scripts/serve.mjs", "/tests/server.test.mjs", "/.git/config",
    "/.env", "/output/private.txt", "/src/.env", "/assets/run.ps1",
    "/src/../README.md", "/src/%2e%2e/README.md", "/assets/%2e%2e/%2e%2e/private.txt",
    "/src/%2e%2e%5cREADME.md", "/src/%252e%252e/README.md", "/src/app.js%00", "/src/app.js::$DATA",
  ]) {
    const response = await get(running.port, path);
    assert.equal(response.status, 403, path);
    assert.doesNotMatch(response.body.toString(), /import \{|"scripts"|repositoryformatversion/);
  }
  const missing = await get(running.port, "/assets/not-a-real-file.png", "HEAD");
  assert.equal(missing.status, 404);
  assert.equal(missing.body.length, 0);
  const blockedHead = await get(running.port, "/package.json", "HEAD");
  assert.equal(blockedHead.status, 403);
  assert.equal(blockedHead.body.length, 0);
  assert.equal((await get(running.port, "/%E0%A4%A")).status, 400);
  const post = await get(running.port, "/index.html", "POST");
  assert.equal(post.status, 405);
  assert.equal(post.headers.allow, "GET, HEAD");
  await running.stop();
  await assert.rejects(get(running.port, "/"), { code: "ECONNREFUSED" });
});

test("the explicit LAN CLI also serves the game at the host's private IPv4 address", async (t) => {
  const running = await start(t, ["--lan"]);
  assert.match(running.output, /同一家庭網路試玩/);
  assert.doesNotMatch(running.output, /Tailscale|100\.93\./);
  assert.equal((await get(running.port, "/manifest.webmanifest")).status, 200);
  const address = lanAddresses()[0]?.address;
  if (address) assert.equal((await get(running.port, "/src/app.js", "GET", address)).status, 200);
  await running.stop();
  await assert.rejects(get(running.port, "/"), { code: "ECONNREFUSED" });
});

test("public-directory junctions cannot expose files outside the game or private root files", async (t) => {
  const temporary = await mkdtemp(join(tmpdir(), "train-preview-"));
  const directory = join(temporary, "game"), privateDirectory = join(temporary, "private");
  let server;
  t.after(async () => {
    if (server) { server.closeAllConnections(); await new Promise((done) => server.close(done)); }
    assert.equal(dirname(temporary), resolve(tmpdir()));
    assert.match(basename(temporary), /^train-preview-/);
    await rm(temporary, { recursive: true, force: true });
  });
  await mkdir(join(directory, "assets"), { recursive: true });
  await mkdir(join(directory, "src"));
  await mkdir(privateDirectory);
  await writeFile(join(directory, "README.md"), "private repository fixture");
  await writeFile(join(privateDirectory, "secret.txt"), "private outside fixture");
  await symlink(privateDirectory, join(directory, "assets", "outside"), "junction");
  await symlink(directory, join(directory, "src", "private-root"), "junction");
  server = await createPreviewServer({ root: directory });
  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  for (const path of ["/assets/outside/secret.txt", "/src/private-root/README.md"])
    assert.equal((await get(server.address().port, path)).status, 403);
});
