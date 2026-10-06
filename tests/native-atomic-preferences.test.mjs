import test from "node:test";
import assert from "node:assert/strict";
import { createAtomicPreferences } from "../src/native-atomic-preferences.js";
import { createNativeStorage } from "../src/native-runtime.js";

const keys = ["passport", "trip"], storageKey = "native.v1";
const envelope = (passport, trip) => JSON.stringify({ version: 1, values: { passport, trip } });
const deferred = () => { let resolve; const promise = new Promise(yes => { resolve = yes; }); return { promise, resolve }; };
const turn = () => new Promise(resolve => setImmediate(resolve));
function realPreferences(initial = {}) {
  const data = new Map(Object.entries(initial)), calls = [];
  return { data, calls,
    async get({ key }) { calls.push(["get", key]); return { value: data.get(key) ?? null }; },
    async set({ key, value }) { calls.push(["set", key, value]); data.set(key, value); },
    async remove({ key }) { calls.push(["remove", key]); data.delete(key); },
  };
}

test("existing envelope reads once and ignores stale legacy and unrelated records", async () => {
  const plugin = realPreferences({ [storageKey]: envelope("new passport", null), passport: "old", trip: "old snapshot", secret: "unrelated" });
  const atomic = await createAtomicPreferences(plugin, { keys, storageKey });
  assert.deepEqual(await atomic.get({ key: "passport" }), { value: "new passport" });
  assert.deepEqual(await atomic.get({ key: "trip" }), { value: null });
  assert.deepEqual(plugin.calls, [["get", storageKey]]); assert.equal(atomic.error, null);
});

test("missing envelope migrates only by read, and first write preserves the entire intended pair without deleting old keys", async () => {
  const plugin = realPreferences({ passport: "old passport", trip: "old snapshot", secret: "unrelated" });
  const atomic = await createAtomicPreferences(plugin, { keys, storageKey });
  assert.deepEqual(plugin.calls, [["get", storageKey], ["get", "passport"], ["get", "trip"]]);
  assert.equal(plugin.data.has(storageKey), false);
  await atomic.set({ key: "passport", value: "updated passport" });
  assert.deepEqual(JSON.parse(plugin.data.get(storageKey)).values, { passport: "updated passport", trip: "old snapshot" });
  assert.equal(plugin.data.get("passport"), "old passport"); assert.equal(plugin.data.get("trip"), "old snapshot"); assert.equal(plugin.data.get("secret"), "unrelated");
  assert.equal(plugin.calls.some(call => call[0] === "remove"), false);
});

test("logical clear keeps an explicit empty envelope so legacy data never resurrects on cold load", async () => {
  const plugin = realPreferences({ passport: "legacy passport", trip: "legacy snapshot" });
  const atomic = await createAtomicPreferences(plugin, { keys, storageKey });
  await atomic.setMany({ values: { passport: null, trip: null } });
  const cold = await createAtomicPreferences(plugin, { keys, storageKey });
  assert.deepEqual(await cold.get({ key: "passport" }), { value: null }); assert.deepEqual(await cold.get({ key: "trip" }), { value: null });
  assert.deepEqual(JSON.parse(plugin.data.get(storageKey)).values, { passport: null, trip: null });
  assert.deepEqual(plugin.calls.at(-1), ["get", storageKey]);
});

test("failed snapshot deletion followed by awarded passport recovers with null snapshot in the same physical write", async () => {
  const oldPassport = '{"trips":0,"giftCredits":0}', awarded = '{"trips":1,"giftCredits":1}';
  const plugin = realPreferences({ [storageKey]: envelope(oldPassport, "solved last station") }), original = plugin.set;
  let fail = true;
  plugin.set = async function (options) { if (fail) { fail = false; throw Error("temporary write fault"); } await original.call(this, options); };
  const atomic = await createAtomicPreferences(plugin, { keys, storageKey });
  await assert.rejects(atomic.remove({ key: "trip" }), TypeError);
  assert.deepEqual(await atomic.get({ key: "trip" }), { value: null });
  assert.deepEqual(JSON.parse(plugin.data.get(storageKey)).values, { passport: oldPassport, trip: "solved last station" });
  await atomic.set({ key: "passport", value: awarded });
  const cold = await createAtomicPreferences(plugin, { keys, storageKey });
  assert.deepEqual(await cold.get({ key: "trip" }), { value: null });
  assert.deepEqual(await cold.get({ key: "passport" }), { value: awarded });
  assert.equal(atomic.error.operation, "write");
});

test("late physical write, logical remove, and new award remain ordered without stale resurrection", async () => {
  const gate = deferred(), plugin = realPreferences({ [storageKey]: envelope("old passport", null) });
  let writes = 0;
  plugin.set = async ({ key, value }) => { plugin.calls.push(["start", key, value]); if (++writes === 1) await gate.promise; plugin.data.set(key, value); };
  const atomic = await createAtomicPreferences(plugin, { keys, storageKey });
  const first = atomic.set({ key: "trip", value: "old snapshot" }), remove = atomic.remove({ key: "trip" }), award = atomic.set({ key: "passport", value: "new award" });
  assert.deepEqual(await atomic.get({ key: "trip" }), { value: null }); await turn(); assert.equal(writes, 1);
  gate.resolve(); await Promise.all([first, remove, award]);
  assert.deepEqual(JSON.parse(plugin.data.get(storageKey)).values, { passport: "new award", trip: null });
  assert.deepEqual(plugin.calls.filter(c => c[0] === "start").map(c => JSON.parse(c[2]).values), [
    { passport: "old passport", trip: "old snapshot" }, { passport: "old passport", trip: null }, { passport: "new award", trip: null },
  ]);
});

test("single finish commit is exactly one physical write: failure leaves old/old; retry succeeds new/null", async () => {
  const old = envelope("old passport", "solved snapshot"), plugin = realPreferences({ [storageKey]: old }), original = plugin.set;
  let reject = true, attempts = 0;
  plugin.set = async function (options) { attempts++; if (reject) throw Error("native unavailable"); await original.call(this, options); };
  const atomic = await createAtomicPreferences(plugin, { keys, storageKey }), storage = await createNativeStorage(atomic, { keys });
  assert.equal(await storage.commit({ passport: "award once", trip: null }), false);
  assert.equal(plugin.data.get(storageKey), old); assert.equal(attempts, 1);
  assert.equal(storage.getItem("passport"), "award once"); assert.equal(storage.getItem("trip"), null);
  reject = false;
  assert.equal(await storage.commit({ passport: "award once", trip: null }), true);
  assert.deepEqual(JSON.parse(plugin.data.get(storageKey)).values, { passport: "award once", trip: null });
  assert.equal(attempts, 2); assert.equal(await storage.flush(), false); // prior error remains observable
  const cold = await createAtomicPreferences(plugin, { keys, storageKey });
  assert.deepEqual(await cold.get({ key: "passport" }), { value: "award once" }); assert.deepEqual(await cold.get({ key: "trip" }), { value: null });
});

test("malformed envelope fails closed and never falls back to legacy or changes any record", async () => {
  const malformed = ["", "not JSON", JSON.stringify({ version: 2, values: { passport: "x", trip: null } }),
    JSON.stringify({ version: 1, values: { passport: "x" } }), JSON.stringify({ version: 1, values: { passport: "x", trip: null, secret: "unknown" } }),
    JSON.stringify({ version: 1, values: { passport: 4, trip: null } }), JSON.stringify({ version: 1, values: { passport: "x", trip: null }, unknown: true })];
  for (const stored of malformed) {
    const plugin = realPreferences({ [storageKey]: stored, passport: "legacy", trip: "private snapshot", secret: "unrelated" });
    const atomic = await createAtomicPreferences(plugin, { keys, storageKey });
    await assert.rejects(atomic.get({ key: "passport" }), TypeError); await assert.rejects(atomic.setMany({ values: { passport: "new", trip: null } }), TypeError);
    await assert.rejects(atomic.remove({ key: "trip" }), TypeError);
    assert.deepEqual(plugin.calls, [["get", storageKey]]); assert.equal(plugin.data.get(storageKey), stored); assert.equal(plugin.data.get("secret"), "unrelated");
  }
});

test("failed or malformed native/legacy reads lock the whole pair; outer adapter still allows in-memory play without native mutation", async () => {
  for (const source of ["envelope", "legacy"]) {
    const plugin = realPreferences({ passport: "old passport", trip: "old snapshot" }), original = plugin.get;
    plugin.get = async function (options) { if ((source === "envelope" && options.key === storageKey) || (source === "legacy" && options.key === "trip")) throw Error("private read error"); return original.call(this, options); };
    const atomic = await createAtomicPreferences(plugin, { keys, storageKey }), storage = await createNativeStorage(atomic, { keys });
    assert.throws(() => storage.commit({ passport: "current play", trip: null }), TypeError);
    assert.equal(storage.getItem("passport"), "current play"); assert.equal(storage.getItem("trip"), null); assert.equal(await storage.flush(), false);
    assert.equal(plugin.calls.some(c => c[0] === "set" || c[0] === "remove"), false); assert.equal(plugin.data.get("trip"), "old snapshot");
  }
});

test("unknown keys, extra fields, accessors and prototype options never touch native preferences", async () => {
  const plugin = realPreferences({ [storageKey]: envelope("p", "t"), secret: "unrelated" }), atomic = await createAtomicPreferences(plugin, { keys, storageKey });
  let evaluated = false;
  for (const values of [{ secret: "changed" }, { passport: 7 }, {}, Object.create({ passport: "inherited" }),
    Object.defineProperty({}, "passport", { enumerable: true, get() { evaluated = true; return "getter"; } })]) await assert.rejects(atomic.setMany({ values }), TypeError);
  await assert.rejects(atomic.set({ key: "passport", value: "changed", unknown: true }), TypeError);
  await assert.rejects(atomic.get({ key: "secret" }), TypeError); await assert.rejects(atomic.remove({ key: "secret" }), TypeError);
  assert.equal(evaluated, false); assert.deepEqual(plugin.calls, [["get", storageKey]]); assert.equal(plugin.data.get("secret"), "unrelated");
  for (const options of [Object.create({ keys, storageKey }), { keys: ["passport", "passport"], storageKey }, { keys, storageKey: "passport" }, { keys, storageKey, unknown: true }]) {
    const untouched = realPreferences(); const locked = await createAtomicPreferences(untouched, options);
    await assert.rejects(locked.get({ key: "passport" }), TypeError); assert.deepEqual(untouched.calls, []);
  }
});

test("atomic values remain exact opaque strings; null logical deletion never calls physical remove", async () => {
  const plugin = realPreferences(), atomic = await createAtomicPreferences(plugin, { keys, storageKey }), literal = '<script>不執行</script>\n"原樣"';
  await atomic.setMany({ values: { passport: literal, trip: null } });
  const cold = await createAtomicPreferences(plugin, { keys, storageKey }); assert.deepEqual(await cold.get({ key: "passport" }), { value: literal });
  assert.equal(plugin.calls.some(c => c[0] === "remove"), false);
});
