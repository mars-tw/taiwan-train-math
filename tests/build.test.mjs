import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { buildSite } from "../scripts/build.mjs";

async function fixture(t) {
  const temporary = await mkdtemp(join(tmpdir(), "train-build-"));
  const root = join(temporary, "game");
  t.after(async () => {
    assert.equal(dirname(temporary), resolve(tmpdir()));
    assert.match(basename(temporary), /^train-build-/);
    await rm(temporary, { recursive: true, force: true });
  });
  await mkdir(root);
  const put = async (path, text = "fixture") => {
    await mkdir(dirname(join(root, path)), { recursive: true });
    await writeFile(join(root, path), text);
  };
  await put("index.html", '<link rel="stylesheet" href="src/main.css?v=1"><script type="module" src="src/main.js?v=1"></script><a href="PRIVACY.md">Privacy</a>');
  await put("manifest.webmanifest", JSON.stringify({ start_url: "./", scope: "./", icons: [{ src: "assets/icon.svg" }] }));
  await put("src/main.js", 'import { value } from "./value.js?v=1"; fetch("data/trains.json?v=1"); export { value };');
  await put("src/value.js", "export const value = 1;");
  await put("src/main.css", 'body { background-image: url("../assets/icon.svg"); }');
  await put("data/trains.json", JSON.stringify({ trains: [{ image: "assets/icon.svg" }] }));
  await put("assets/icon.svg", '<svg xmlns="http://www.w3.org/2000/svg"></svg>');
  for (const path of ["docs/credits.md", "LICENSE", "NOTICE", "ASSET-LICENSE.md", "PRIVACY.md"]) await put(path);
  return { root, temporary, put, read: (path) => readFile(join(root, path), "utf8") };
}

test("a second build removes deleted assets and old output without publishing repository files", async (t) => {
  const { root, put, read } = await fixture(t);
  for (const path of ["README.md", "package.json", "scripts/local.mjs", "tests/local.test.mjs", ".git/config", "src/.env", "data/.cache/local.json"])
    await put(path, "private fixture");
  await put("assets/old.svg", "old asset");
  await buildSite(root);
  assert.equal(await read("dist/assets/old.svg"), "old asset");
  await put("dist/private.txt", "leftover output");
  await rm(join(root, "assets/old.svg"));
  await put("src/value.js", "export const value = 2;");
  await buildSite(root);
  assert.equal(await read("dist/src/value.js"), "export const value = 2;");
  assert.equal(await read("dist/PRIVACY.md"), "fixture");
  for (const path of ["assets/old.svg", "private.txt", "README.md", "package.json", "scripts/local.mjs", "tests/local.test.mjs", ".git/config", "src/.env", "data/.cache/local.json"])
    await assert.rejects(read(`dist/${path}`), { code: "ENOENT" });
});

test("broken HTML, module, CSS, manifest and data references preserve the last build", async (t) => {
  for (const [owner, source] of [
    ["index.html", '<script src="src/missing.js"></script>'],
    ["src/main.js", 'import "./Missing.js";'],
    ["src/main.js", 'export { value } from "./missing.js";'],
    ["src/main.js", 'const load = () => import("./missing.js");'],
    ["src/main.css", 'body { background: url("../assets/missing.svg"); }'],
    ["manifest.webmanifest", '{"icons":[{"src":"assets/missing.svg"}]}'],
    ["data/trains.json", '{"trains":[{"referencePhoto":{"path":"assets/missing.jpg"}}]}'],
  ]) {
    const { root, put, read } = await fixture(t);
    await buildSite(root);
    await put("dist/last-success.txt", "previous build");
    await put(owner, source);
    await assert.rejects(buildSite(root), /找不到公開素材/, owner);
    assert.equal(await read("dist/last-success.txt"), "previous build", owner);
  }
});

test("project Pages references reject root paths, escapes and case mismatches", async (t) => {
  for (const reference of ["/src/main.js", "../src/main.js", "src/Main.js", "src/%2e%2e/%2e%2e/private.js"]) {
    const { root, put } = await fixture(t);
    await put("index.html", `<script src="${reference}"></script>`);
    await assert.rejects(buildSite(root), /相對路徑|超出專案|找不到公開素材/, reference);
  }
});

test("query strings, external links, data URLs and hashes remain valid", async (t) => {
  const { root, put, read } = await fixture(t);
  await put("index.html", '<script src="src/main.js?v=2&amp;lang=zh"></script><a href="#home">Home</a><a href="https://example.invalid/source">Source</a><img src="data:image/svg+xml,example">');
  await put("src/main.css", 'body { background: url("data:image/svg+xml,example"); mask: url(#mask); }');
  await buildSite(root);
  assert.equal(await read("dist/index.html"), await read("index.html"));
});

test("public junctions are rejected before they can copy files outside the project", async (t) => {
  const { root, temporary, put, read } = await fixture(t);
  const outside = join(temporary, "outside");
  await mkdir(outside);
  await writeFile(join(outside, "private.txt"), "outside file");
  await put("dist/last-success.txt", "previous build");
  await symlink(outside, join(root, "assets", "linked"), "junction");
  await assert.rejects(buildSite(root), /公開素材不能是符號連結或目錄連結/);
  assert.equal(await read("dist/last-success.txt"), "previous build");
  assert.equal(await readFile(join(outside, "private.txt"), "utf8"), "outside file");
});

test("a linked dist target is rejected without removing or writing its external contents", async (t) => {
  const { root, temporary } = await fixture(t);
  const outside = join(temporary, "outside");
  await mkdir(outside);
  await writeFile(join(outside, "private.txt"), "outside file");
  await symlink(outside, join(root, "dist"), "junction");
  await assert.rejects(buildSite(root), /dist 必須是專案內的一般目錄/);
  assert.equal(await readFile(join(outside, "private.txt"), "utf8"), "outside file");
  await assert.rejects(readFile(join(outside, "index.html")), { code: "ENOENT" });
});
