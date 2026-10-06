import test from "node:test";
import assert from "node:assert/strict";
import { isNativeHost, backAction, safeExternalUrl, createNativeStorage, attachNativeLifecycle } from "../src/native-runtime.js";

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const turn = () => new Promise(resolve => setImmediate(resolve));
function preferences(initial = {}) {
  const data = new Map(Object.entries(initial)), calls = [];
  return { data, calls,
    async get({ key }) { calls.push(["get", key]); return { value: data.get(key) ?? null }; },
    async set({ key, value }) { calls.push(["set", key, value]); data.set(key, value); },
    async remove({ key }) { calls.push(["remove", key]); data.delete(key); },
  };
}

test("native detection requires a truthful platform bridge, accepts direct or window host, and fails closed", () => {
  for (const platform of ["android", "ios"]) {
    const bridge = { isNativePlatform: () => true, getPlatform: () => platform };
    assert.equal(isNativeHost(bridge), true); assert.equal(isNativeHost({ Capacitor: bridge }), true);
  }
  for (const host of [null, {}, { isNative: true }, { isNativePlatform: () => true, getPlatform: () => "web" },
    { isNativePlatform: () => "true", getPlatform: () => "android" },
    { isNativePlatform() { throw Error("not ready"); }, getPlatform: () => "ios" }]) assert.equal(isNativeHost(host), false);
  assert.equal(isNativeHost(Object.defineProperty({}, "Capacitor", { get() { throw Error("blocked"); } })), false);
});

test("back closes overlays before preserving game work, and root never follows stale browser history", () => {
  assert.equal(backAction({ dialogOpen: true, storyMenuOpen: true, view: "game" }), "close-dialog");
  assert.equal(backAction({ dialogOpen: false, storyMenuOpen: true, view: "game" }), "close-story");
  assert.equal(backAction({ view: "game" }), "pause-trip");
  for (const view of ["playroom", "collection", "stamps", "finish"]) assert.equal(backAction({ view }), "go-home");
  assert.equal(backAction({ view: "home" }), "minimize");
  assert.equal(backAction(Object.create({ dialogOpen: true, view: "game" })), "minimize");
  assert.equal(backAction({ get view() { throw Error("getter must not run"); } }), "minimize");
  assert.equal(backAction({ dialogOpen: "true", view: "home" }), "minimize");
});

test("external URLs normalize public https only and do not navigate app assets or unsafe destinations", () => {
  assert.equal(safeExternalUrl("https://example.org/a?x=1#source", "capacitor://localhost/"), "https://example.org/a?x=1#source");
  assert.equal(safeExternalUrl(" https://EXAMPLE.org:443/credits ", "https://localhost/"), "https://example.org/credits");
  for (const href of ["", "#credits", "docs/credits.md", "https://localhost/x", "https://LOCALHOST./x",
    "https://app.localhost/", "https://127.1/x", "https://0x7f000001/", "https://[::1]/", "https://[::ffff:127.2.3.4]/", "https://0.0.0.0/",
    "file:///credits", "javascript:alert(1)", "data:text/html,hello", "http://example.org/", "https://user:secret@example.org/",
    "https://@example.org/", "//example.org/", "https://example.\norg/", "https://example.org/" + "a".repeat(4096)]) assert.equal(safeExternalUrl(href, "https://localhost/"), null, href);
  assert.equal(safeExternalUrl("/credits", "https://example.org/app/"), null);
  assert.equal(safeExternalUrl("https://example.org/x", "https://example.org/app/"), null);
  assert.equal(safeExternalUrl({ toString() { throw Error("coercion"); } }, "https://localhost/"), null);
  assert.equal(safeExternalUrl("https://example.org/", "invalid base"), null);
});

test("storage waits for hydration, exposes synchronous opaque values, and touches only configured keys", async () => {
  const pending = deferred(), plugin = preferences({ passport: '{"trips":3}', secret: "do not read" });
  plugin.get = async ({ key }) => { plugin.calls.push(["get", key]); return key === "trip" ? pending.promise : { value: plugin.data.get(key) ?? null }; };
  let ready = false;
  const preparing = createNativeStorage(plugin, { keys: ["passport", "trip"] }).then(storage => { ready = true; return storage; });
  await turn(); assert.equal(ready, false); pending.resolve({ value: "opaque snapshot string" });
  const storage = await preparing;
  assert.equal(storage.getItem("passport"), '{"trips":3}'); assert.equal(storage.getItem("trip"), "opaque snapshot string");
  assert.deepEqual(plugin.calls, [["get", "passport"], ["get", "trip"]]); assert.equal(storage.error, null);
  storage.setItem("passport", '{"trips":4}'); assert.equal(storage.getItem("passport"), '{"trips":4}');
  assert.equal(await storage.flush(), true); assert.equal(plugin.data.get("passport"), '{"trips":4}'); assert.equal(plugin.data.get("secret"), "do not read");
});

test("late set cannot resurrect a removed snapshot; all keys share one ordered write queue", async () => {
  const gate = deferred(), plugin = preferences();
  const set = plugin.set;
  plugin.set = async function (options) { plugin.calls.push(["set-start", options.key]); if (options.value === "old snapshot") await gate.promise; await set.call(plugin, options); };
  const storage = await createNativeStorage(plugin, { keys: ["trip", "passport"] });
  storage.setItem("trip", "old snapshot"); storage.removeItem("trip"); storage.setItem("passport", "awarded once");
  assert.equal(storage.getItem("trip"), null); assert.equal(storage.getItem("passport"), "awarded once");
  let flushed = false; const flushing = storage.flush().then(ok => { flushed = true; return ok; });
  await turn(); assert.equal(flushed, false); assert.equal(plugin.calls.some(c => c[0] === "remove"), false);
  gate.resolve(); assert.equal(await flushing, true);
  assert.equal(plugin.data.has("trip"), false); assert.equal(plugin.data.get("passport"), "awarded once");
  assert.deepEqual(plugin.calls.filter(c => ["set", "remove"].includes(c[0])), [["set", "trip", "old snapshot"], ["remove", "trip"], ["set", "passport", "awarded once"]]);
});

test("remove then a new explicit snapshot persists only the newer trip, including writes during flush", async () => {
  const gate = deferred(), plugin = preferences(); plugin.set = async ({ key, value }) => { if (value === "one") await gate.promise; plugin.data.set(key, value); };
  const storage = await createNativeStorage(plugin, { keys: ["trip"] });
  storage.setItem("trip", "one"); const flushing = storage.flush(); await turn();
  storage.removeItem("trip"); storage.setItem("trip", "new trip"); gate.resolve();
  assert.equal(await flushing, true); assert.equal(plugin.data.get("trip"), "new trip"); assert.equal(storage.getItem("trip"), "new trip");
});

test("malformed or failed hydrate stays read-only, gives null, and reports no secret payload", async () => {
  const reports = [], plugin = preferences({ secret: "preserve" });
  plugin.get = async ({ key }) => { if (key === "trip") throw Error("private native exception"); return { value: 42 }; };
  const storage = await createNativeStorage(plugin, { keys: ["trip", "passport"], onError: failure => reports.push(failure) });
  assert.equal(storage.getItem("trip"), null); assert.equal(storage.getItem("passport"), null); assert.equal(await storage.flush(), false);
  assert.equal(plugin.data.get("secret"), "preserve"); assert.deepEqual(plugin.calls, []);
  assert.equal(reports.length, 2); assert.equal(reports.every(r => r.operation === "hydrate"), true);
  assert.equal(JSON.stringify(reports).includes("private native exception"), false); assert.equal(Object.isFrozen(storage.error), true);
});

test("prototype/getter malformed response is never read or cleared", async () => {
  let getterCalls = 0;
  for (const response of [undefined, { other: null }, Object.create({ value: "inherited" }),
    Object.defineProperty({}, "value", { enumerable: true, get() { getterCalls++; return "secret"; } }),
    { value: "oversized".repeat(20000) }]) {
    const plugin = preferences(); plugin.get = async () => response;
    const storage = await createNativeStorage(plugin, { keys: ["trip"] });
    assert.equal(storage.getItem("trip"), null); assert.equal(storage.error.operation, "hydrate"); assert.equal(await storage.flush(), false);
    assert.deepEqual(plugin.calls, []);
  }
  assert.equal(getterCalls, 0);
});

test("unreadable native keys stay durably read-only while in-memory play and other valid keys continue", async () => {
  for (const failure of ["reject", "malformed"]) {
    const plugin = preferences({ trip: "unread old snapshot", passport: "old passport", secret: "unrelated" }), get = plugin.get;
    plugin.get = async function ({ key }) {
      if (key === "trip") { this.calls.push(["get", key]); if (failure === "reject") throw Error("cannot read private record"); return { value: 7 }; }
      return get.call(this, { key });
    };
    const storage = await createNativeStorage(plugin, { keys: ["trip", "passport"] });
    assert.equal(storage.getItem("trip"), null);
    assert.throws(() => storage.setItem("trip", "current-session work"), TypeError);
    assert.equal(storage.getItem("trip"), "current-session work");
    assert.throws(() => storage.removeItem("trip"), TypeError);
    assert.equal(storage.getItem("trip"), null);
    storage.setItem("passport", "new valid passport");
    assert.equal(await storage.flush(), false);
    assert.equal(plugin.data.get("trip"), "unread old snapshot");
    assert.equal(plugin.data.get("passport"), "new valid passport");
    assert.equal(plugin.data.get("secret"), "unrelated");
    assert.deepEqual(plugin.calls.filter(c => c[0] !== "get"), [["set", "passport", "new valid passport"]]);
    assert.equal(storage.error.operation, "hydrate");
  }
});

test("native write failure is sticky and observable; later remove still runs without falsely reporting durability", async () => {
  const reports = [], plugin = preferences({ trip: "old" }); plugin.set = async () => { throw Error("native database secret"); };
  const storage = await createNativeStorage(plugin, { keys: ["trip"], onError: info => { reports.push(info); throw Error("UI callback failure"); } });
  storage.setItem("trip", "new"); assert.equal(storage.getItem("trip"), "new"); storage.removeItem("trip");
  assert.equal(await storage.flush(), false); assert.equal(plugin.data.has("trip"), false); assert.equal(storage.getItem("trip"), null);
  assert.deepEqual(storage.error, { operation: "set", key: "trip" }); assert.deepEqual(reports, [{ operation: "set", key: "trip" }]);
  assert.equal(await storage.flush(), false);
});

test("failed remove cannot claim the snapshot was durably cleared", async () => {
  const plugin = preferences({ trip: "old" }); plugin.remove = async () => { throw Error("device locked"); };
  const storage = await createNativeStorage(plugin, { keys: ["trip"] }); storage.removeItem("trip");
  assert.equal(storage.getItem("trip"), null); assert.equal(await storage.flush(), false); assert.equal(plugin.data.get("trip"), "old"); assert.equal(storage.error.operation, "remove");
});

test("invalid options, unsupported bridges, unknown keys and coercible values fail closed without touching unrelated preferences", async () => {
  const badKeys = [[], ["trip", "trip"], ["__proto__"], Array(2), Object.assign(["trip"], { extra: true })];
  for (const keys of badKeys) { const plugin = preferences(); const storage = await createNativeStorage(plugin, { keys }); assert.equal(await storage.flush(), false); assert.deepEqual(plugin.calls, []); }
  const plugin = preferences(); const options = Object.create({ keys: ["secret"] });
  const bad = await createNativeStorage(plugin, options); assert.equal(bad.getItem("secret"), null); assert.deepEqual(plugin.calls, []);
  const storage = await createNativeStorage(plugin, { keys: ["trip"] });
  assert.equal(storage.getItem("secret"), null); assert.throws(() => storage.setItem("secret", "new"), TypeError); assert.throws(() => storage.removeItem("secret"), TypeError);
  let coerced = false; assert.throws(() => storage.setItem("trip", { toString() { coerced = true; return "secret"; } }), TypeError); assert.equal(coerced, false);
  const unavailable = await createNativeStorage(null, { keys: ["trip"] }); assert.equal(unavailable.getItem("trip"), null); assert.throws(() => unavailable.setItem("trip", "new"), TypeError); assert.equal(await unavailable.flush(), false);
  let bound = false;
  const malformed = await createNativeStorage({ get: { bind() { bound = true; return async () => ({ value: "secret" }); } }, async set() {}, async remove() {} }, { keys: ["trip"] });
  assert.equal(bound, false); assert.equal(malformed.getItem("trip"), null); assert.equal(await malformed.flush(), false);
});

function appPlugin() {
  const listeners = new Map(), removed = [];
  return { listeners, removed,
    async addListener(name, callback) { listeners.set(name, callback); return { async remove() { removed.push(name); } }; },
  };
}

test("inactive edge pauses once, active only rearms, back dispatches, and cleanup ignores late callbacks", async () => {
  const app = appPlugin(); let paused = 0, backs = 0;
  const cleanup = await attachNativeLifecycle(app, { onPause: () => paused++, onBack: () => backs++ });
  const state = app.listeners.get("appStateChange"), back = app.listeners.get("backButton");
  state({ isActive: false }); state({ isActive: false }); assert.equal(paused, 1);
  state({ isActive: true }); assert.equal(paused, 1); state({ isActive: false }); assert.equal(paused, 2);
  state({ isActive: "false" }); state(Object.create({ isActive: true })); assert.equal(paused, 2);
  back({ canGoBack: true }); assert.equal(backs, 1);
  assert.equal(await cleanup(), true); assert.equal(await cleanup(), true);
  state({ isActive: true }); state({ isActive: false }); back(); assert.equal(paused, 2); assert.equal(backs, 1);
  assert.deepEqual(app.removed, ["appStateChange", "backButton"]);
});

test("listener registration and callback failures cannot leak live callbacks or uncaught rejections", async () => {
  const app = appPlugin(); const original = app.addListener;
  app.addListener = async function (name, callback) { if (name === "backButton") throw Error("registration failed"); return original.call(app, name, callback); };
  let paused = 0; const cleanup = await attachNativeLifecycle(app, { onPause: () => paused++, onBack() {} });
  app.listeners.get("appStateChange")({ isActive: false }); assert.equal(paused, 0); assert.equal(await cleanup(), false); assert.deepEqual(app.removed, ["appStateChange"]);
  const healthy = appPlugin(); const dispose = await attachNativeLifecycle(healthy, { onPause() { throw Error("UI failed"); }, onBack: async () => { throw Error("async UI failed"); } });
  healthy.listeners.get("appStateChange")({ isActive: false }); healthy.listeners.get("backButton")(); await turn(); assert.equal(await dispose(), true);
});

test("cleanup detaches all owned listeners even if one removal fails; invalid options never register", async () => {
  const removed = [], app = { async addListener(name) { return { async remove() { removed.push(name); if (name === "appStateChange") throw Error("detached native side"); } }; } };
  const cleanup = await attachNativeLifecycle(app, { onPause() {}, onBack() {} }); assert.equal(await cleanup(), false); assert.deepEqual(removed, ["appStateChange", "backButton"]);
  const healthy = appPlugin(); const noop = await attachNativeLifecycle(healthy, Object.create({ onPause() {} })); assert.equal(await noop(), false); assert.equal(healthy.listeners.size, 0);
});

test("missing callbacks never override native back, and symbol/accessor options fail without evaluation", async () => {
  for (const callbacks of [{}, { onPause() {} }, { onBack() {} }, { onPause: true, onBack() {} }]) {
    const app = appPlugin(); const cleanup = await attachNativeLifecycle(app, callbacks); assert.equal(await cleanup(), false); assert.equal(app.listeners.size, 0);
  }
  let read = 0; const options = { keys: ["trip"], get onError() { read++; return () => {}; } };
  const plugin = preferences(); const storage = await createNativeStorage(plugin, options);
  assert.equal(await storage.flush(), false); assert.equal(read, 0); assert.deepEqual(plugin.calls, []);
  const symbolOptions = { keys: ["trip"], [Symbol("unexpected")]: "secret" };
  const symbolStore = await createNativeStorage(plugin, symbolOptions); assert.equal(await symbolStore.flush(), false); assert.deepEqual(plugin.calls, []);
});

test("commit updates memory synchronously and submits exactly one complete logical batch", async () => {
  const plugin = preferences({ passport: "old", trip: "solved" }), gate = deferred(), calls = [];
  plugin.setMany = async ({ values }) => { calls.push({ ...values }); await gate.promise; for (const [key, value] of Object.entries(values)) value === null ? plugin.data.delete(key) : plugin.data.set(key, value); };
  const storage = await createNativeStorage(plugin, { keys: ["passport", "trip"] });
  const saving = storage.commit({ passport: "awarded", trip: null });
  assert.equal(storage.getItem("passport"), "awarded"); assert.equal(storage.getItem("trip"), null); await turn(); assert.equal(calls.length, 1);
  gate.resolve(); assert.equal(await saving, true); assert.deepEqual(calls, [{ passport: "awarded", trip: null }]);
  assert.equal(plugin.data.get("passport"), "awarded"); assert.equal(plugin.data.has("trip"), false);
});

test("commit result describes that transaction while flush retains earlier failure; failed batch can retry", async () => {
  const plugin = preferences(); let failing = true;
  plugin.setMany = async () => { if (failing) throw Error("commit failed"); };
  const storage = await createNativeStorage(plugin, { keys: ["passport", "trip"] });
  assert.equal(await storage.commit({ passport: "award", trip: null }), false); assert.equal(storage.error.operation, "commit");
  failing = false; assert.equal(await storage.commit({ passport: "award", trip: null }), true); assert.equal(await storage.flush(), false);
});

test("unreadable batch throws synchronously without backend mutation, and invalid batches never partially update memory", async () => {
  const plugin = preferences({ passport: "old", trip: "unread" }); let batches = 0;
  plugin.get = async ({ key }) => { if (key === "trip") throw Error("read failed"); return { value: "old" }; };
  plugin.setMany = async () => batches++;
  const storage = await createNativeStorage(plugin, { keys: ["passport", "trip"] });
  assert.throws(() => storage.commit({ passport: "current play", trip: null }), TypeError);
  assert.equal(storage.getItem("passport"), "current play"); assert.equal(storage.getItem("trip"), null); assert.equal(batches, 0);
  for (const values of [{ secret: "x" }, { passport: 9 }, {}, Object.create({ passport: "inherited" })]) assert.throws(() => storage.commit(values), TypeError);
  assert.equal(storage.getItem("passport"), "current play"); assert.equal(await storage.flush(), false); assert.equal(plugin.data.get("trip"), "unread");
});
