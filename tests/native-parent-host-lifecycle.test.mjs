import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { createParentChallenge, matchesParentChallenge, classifyNativeResourceLink } from "../src/native-parent-access.js";

// Exercise the actual native host with bridge and DOM substitutes. Its import
// declarations are replaced by the same named dependencies in the sandbox.
const source = readFileSync(new URL("../native/host-entry.js", import.meta.url), "utf8");
const hostScript = source.replace(/^import [^\n]+\r?\n/gm, "");
assert.equal((source.match(/^import /gm) || []).length, 7);

class Target {
  listeners = new Map();
  addEventListener(name, callback) {
    if (!this.listeners.has(name)) this.listeners.set(name, []);
    this.listeners.get(name).push(callback);
  }
  emit(name, event = {}) {
    for (const callback of this.listeners.get(name) || []) callback(event);
  }
}

class Element extends Target {
  nodes = new Map();
  open = false;
  textContent = "";
  value = "";
  children = [];
  querySelector(selector) {
    if (!this.nodes.has(selector)) this.nodes.set(selector, new Element());
    return this.nodes.get(selector);
  }
  setAttribute() {}
  replaceChildren(...children) { this.children = children; }
  showModal() { this.open = true; }
  close() {
    if (!this.open) return;
    this.open = false;
    this.emit("close");
  }
}

function harness({ stopSpeech = async () => {} } = {}) {
  const elements = new Map();
  const about = new Element(); about.id = "about-dialog"; elements.set("#about-dialog", about);
  const resources = new Element(); resources.id = "native-parent-resources"; elements.set("#native-parent-resources", resources);
  const announcement = new Element(); elements.set("#announcement", announcement);
  const document = new Target();
  document.readyState = "complete";
  document.hidden = false;
  document.querySelector = selector => elements.get(selector) || null;
  document.createElement = () => new Element();
  document.createTextNode = text => ({ text });
  document.body = { append(element) { elements.set(`#${element.id}`, element); } };
  const window = new Target();
  window.crypto = { getRandomValues(values) { values[0] = 16; values[1] = 3; return values; } };
  window.TrainMathNativeDocuments = { "PRIVACY.md": "local privacy" };
  window.dispatchEvent = event => window.emit(event.type, event);
  const opened = [];
  let appStateChange;
  const App = { addListener(name, callback) {
    if (name === "appStateChange") appStateChange = callback;
    return Promise.resolve({ remove() {} });
  } };
  const OfflineSpeech = { stop: stopSpeech, getStatus: async () => ({ available: false, offline: true }) };
  runInNewContext(hostScript, {
    window, document, location: { href: "capacitor://localhost/index.html" },
    Capacitor: { isNativePlatform: () => true }, registerPlugin: () => OfflineSpeech,
    App, Preferences: {}, Browser: { async open({ url }) { opened.push(url); } },
    createNativeStorage: async () => ({ flush: async () => true }), createAtomicPreferences: async () => ({}),
    createParentChallenge, matchesParentChallenge, classifyNativeResourceLink,
    URL, Promise, Event, Uint32Array,
  });
  const host = window.TrainMathNative;
  const gate = () => elements.get("#native-parent-gate");
  const submit = async answer => {
    gate().querySelector("#native-gate-answer").value = answer;
    await gate().querySelector("#native-gate-form").onsubmit({ preventDefault() {} });
  };
  const openParent = async () => {
    host.openParentArea(() => resources.replaceChildren({ text: "source list" }));
    assert.equal(gate().open, true);
    await submit("261");
    assert.equal(about.open, true);
    assert.equal(host.parentAreaAuthorized, true);
  };
  const click = href => {
    const link = {
      getAttribute(name) { return name === "href" ? href : null; },
      closest(selector) {
        if (selector === "a[href]") return this;
        return selector === "#about-dialog[open]" && about.open ? about : null;
      },
    };
    let prevented = false;
    document.emit("click", { target: link, preventDefault() { prevented = true; }, stopImmediatePropagation() {} });
    return prevented;
  };
  return { window, document, host, about, resources, gate, submit, openParent, click, opened,
    nativePause() { appStateChange({ isActive: false }); }, nativeResume() { appStateChange({ isActive: true }); } };
}

test("cancel and wrong answers never grant access; each correct answer opens only its clicked source", async () => {
  const ui = harness();
  ui.host.openParentArea(() => {});
  ui.gate().close();
  assert.equal(ui.host.parentAreaAuthorized, false);
  ui.host.openParentArea(() => {});
  await ui.submit("260");
  assert.equal(ui.gate().open, true);
  assert.equal(ui.about.open, false);
  assert.equal(ui.host.parentAreaAuthorized, false);
  await ui.submit("261");
  assert.equal(ui.about.open, true);
  assert.equal(ui.host.parentAreaAuthorized, true);
  assert.equal(ui.click("https://example.org/first"), true);
  await ui.submit("260");
  assert.deepEqual(ui.opened, []);
  await ui.submit("261");
  await ui.submit("261");
  assert.deepEqual(ui.opened, ["https://example.org/first"]);
  assert.equal(ui.click("https://example.org/second"), true);
  assert.deepEqual(ui.opened, ["https://example.org/first"]);
  ui.gate().close();
  assert.deepEqual(ui.opened, ["https://example.org/first"]);
  assert.equal(ui.click("https://example.org/second"), true);
  await ui.submit("261");
  assert.deepEqual(ui.opened, ["https://example.org/first", "https://example.org/second"]);
});

test("blur, hidden, pagehide, native pause or resume, and closing the modal revoke the open parent area", async () => {
  const triggers = [
    ui => ui.window.emit("blur"),
    ui => { ui.document.hidden = true; ui.document.emit("visibilitychange"); ui.document.hidden = false; },
    ui => ui.window.emit("pagehide"),
    ui => ui.nativePause(),
    ui => ui.nativeResume(),
    ui => ui.about.close(),
  ];
  for (const trigger of triggers) {
    const ui = harness();
    await ui.openParent();
    trigger(ui);
    assert.equal(ui.about.open, false);
    assert.equal(ui.host.parentAreaAuthorized, false);
    assert.deepEqual(ui.resources.children, []);
    assert.equal(ui.click("https://example.org/first"), true);
    assert.deepEqual(ui.opened, []);
    assert.equal(ui.gate().open, false);
    // Fresh launch initializes a locked host even when the earlier page was open.
    assert.equal(harness().host.parentAreaAuthorized, false);
  }
});

test("background during asynchronous approval cannot reopen parent resources or launch a stale link", async () => {
  let release;
  let waitForSpeech = false;
  const ui = harness({ stopSpeech: () => waitForSpeech ? new Promise(resolve => { release = resolve; }) : Promise.resolve() });
  await ui.openParent();
  assert.equal(ui.click("https://example.org/first"), true);
  waitForSpeech = true;
  const pending = ui.submit("261");
  ui.nativePause();
  release();
  await pending;
  assert.deepEqual(ui.opened, []);
  assert.equal(ui.host.parentAreaAuthorized, false);
  assert.equal(ui.about.open, false);
});

test("background closes an unanswered challenge and cancels a delayed parent-area approval", async () => {
  let release;
  const ui = harness({ stopSpeech: () => new Promise(resolve => { release = resolve; }) });
  ui.host.openParentArea(() => {});
  ui.window.emit("blur");
  assert.equal(ui.gate().open, false);
  await ui.submit("261");
  assert.equal(ui.about.open, false);
  ui.host.openParentArea(() => {});
  const pending = ui.submit("261");
  ui.document.hidden = true;
  ui.document.emit("visibilitychange");
  release();
  await pending;
  assert.equal(ui.about.open, false);
  assert.equal(ui.host.parentAreaAuthorized, false);
});
