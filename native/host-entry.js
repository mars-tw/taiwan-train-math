import { Capacitor, registerPlugin } from "@capacitor/core";
import { App } from "@capacitor/app";
import { Preferences } from "@capacitor/preferences";
import { Browser } from "@capacitor/browser";
import { createNativeStorage } from "../src/native-runtime.js";
import { createAtomicPreferences } from "../src/native-atomic-preferences.js";
import { createParentChallenge, matchesParentChallenge, classifyNativeResourceLink } from "../src/native-parent-access.js";

const OfflineSpeech = registerPlugin("OfflineSpeech");
let parentAreaAuthorized = false;
const host = window.TrainMathNative = {
  Capacitor, App, native: Capacitor.isNativePlatform(), storage: null,
  get parentAreaAuthorized() { return parentAreaAuthorized; },
  speechAvailable: false, speechError: null,
  async cancelSpeech() { if (host.native) await OfflineSpeech.stop().catch(() => {}); },
  async speak(text) {
    if (!host.native || !host.speechAvailable) return false;
    try { await OfflineSpeech.speak({ text: String(text).slice(0, 3000) }); return true; }
    catch { host.speechError = "這台裝置的中文語音暫時不可用，仍可看畫面繼續玩。"; return false; }
  },
  async minimize() { await App.minimizeApp(); },
};
host.ready = (async () => {
  if (!host.native) return host;
  const atomic = await createAtomicPreferences(Preferences, {
    keys: ["taiwan-train-math.v1", "taiwan-train-math.session.v1"],
    storageKey: "taiwan-train-math.native.v1",
  });
  host.storage = await createNativeStorage(atomic, {
    keys: ["taiwan-train-math.v1", "taiwan-train-math.session.v1"],
    onError() { host.storageFailed = true; window.dispatchEvent(new Event("train-native-storage-error")); },
  });
  OfflineSpeech.getStatus().then(status => {
    host.speechAvailable = status.available === true && status.offline === true;
    window.dispatchEvent(new Event("train-native-voice"));
  }).catch(() => { host.speechAvailable = false; });
  return host;
})();

function message(text) {
  document.querySelector("#announcement")?.replaceChildren(document.createTextNode(text));
}
let parentAccessEpoch = 0;
function revokeParentAccess() {
  parentAccessEpoch++;
  parentAreaAuthorized = false;
  for (const selector of ["#native-parent-gate", "#native-document-dialog", "#about-dialog"]) {
    const dialog = document.querySelector(selector);
    if (dialog?.open) dialog.close();
  }
  document.querySelector("#native-parent-resources")?.replaceChildren();
}
if (host.native) {
  window.addEventListener("blur", revokeParentAccess);
  window.addEventListener("pagehide", revokeParentAccess);
  document.addEventListener("visibilitychange", () => { if (document.hidden) revokeParentAccess(); });
  try {
    // Revoke on either edge, so a missed inactive event cannot preserve an
    // unlocked modal when the native bridge reports that the app is active.
    Promise.resolve(App.addListener("appStateChange", revokeParentAccess)).catch(() => {});
  } catch {}
}
function parentGate(onApproved, destination) {
  const challenge = createParentChallenge(values => window.crypto.getRandomValues(values));
  if (!challenge) { message("家長驗證暫時無法使用，請稍後再試。"); return; }
  const accessEpoch = parentAccessEpoch;
  let dialog = document.querySelector("#native-parent-gate");
  if (!dialog) {
    dialog = document.createElement("dialog"); dialog.id = "native-parent-gate";
    dialog.setAttribute("aria-labelledby", "native-gate-title");
    dialog.innerHTML = '<form method="dialog" class="dialog-head"><h2 id="native-gate-title">請交給家長</h2><button class="close-btn" aria-label="回到遊戲">×</button></form><p>此區可查看素材來源與授權，部分連結會開啟外部網站。請家長確認後再繼續。</p><form id="native-gate-form"><label for="native-gate-answer" id="native-gate-question"></label><input id="native-gate-answer" type="text" inputmode="numeric" autocomplete="off"><p id="native-gate-result" role="status"></p><button class="primary-btn" type="submit">家長確認，開啟資料</button></form>';
    document.body.append(dialog);
  }
  dialog.querySelector("#native-gate-question").textContent = `請家長計算：${challenge.first} × ${challenge.second} ＝？`;
  dialog.querySelector("#native-gate-answer").value = "";
  dialog.querySelector("#native-gate-title").textContent = `請交給家長 · ${destination}`;
  dialog.querySelector("#native-gate-result").textContent = "";
  let completed = false;
  dialog.querySelector("#native-gate-form").onsubmit = async event => {
    event.preventDefault();
    if (completed || !dialog.open || accessEpoch !== parentAccessEpoch || document.hidden) return;
    if (!matchesParentChallenge(challenge, dialog.querySelector("#native-gate-answer").value)) {
      dialog.querySelector("#native-gate-result").textContent = "請家長再確認，或關閉回到遊戲。"; return;
    }
    completed = true; dialog.close(); await host.cancelSpeech();
    if (accessEpoch !== parentAccessEpoch || document.hidden) return;
    try { await onApproved(); } catch { message("家長資料暫時無法開啟，請稍後再試。"); }
  };
  dialog.showModal();
}

host.openParentArea = onOpen => {
  if (!host.native || typeof onOpen !== "function") return;
  parentGate(() => {
    const about = document.querySelector("#about-dialog");
    if (!about || about.open) return;
    onOpen();
    about.querySelector("#about-title").textContent = "家長資料與授權";
    about.showModal();
    parentAreaAuthorized = true;
  }, "遊戲資料與授權");
};
function attachParentClose() {
  document.querySelector("#about-dialog")?.addEventListener("close", revokeParentAccess);
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", attachParentClose, { once: true });
else attachParentClose();

function showLocalDocument(url) {
  const path = new URL(url, location.href).pathname.replace(/^\//, "");
  const map = window.TrainMathNativeDocuments || {};
  const content = map[path];
  if (!content) { message("這份資料尚未包入 App。" ); return; }
  let dialog = document.querySelector("#native-document-dialog");
  if (!dialog) {
    dialog = document.createElement("dialog"); dialog.id = "native-document-dialog";
    dialog.setAttribute("aria-label", "遊戲資料與授權");
    dialog.innerHTML = '<form method="dialog" class="dialog-head"><h2>遊戲資料與授權</h2><button class="close-btn" aria-label="關閉資料">×</button></form><pre class="native-document-text"></pre>';
    document.body.append(dialog);
  }
  dialog.querySelector("pre").textContent = content; dialog.showModal();
}

document.addEventListener("click", event => {
  if (!host.native) return;
  const link = event.target.closest?.("a[href]"); if (!link) return;
  const href = link.getAttribute("href"); if (!href || href.startsWith("#")) return;
  event.preventDefault(); event.stopImmediatePropagation();
  const decision = classifyNativeResourceLink(href, location.href, window.TrainMathNativeDocuments,
    { authorized: host.parentAreaAuthorized, inParentArea: !!link.closest("#about-dialog[open]") });
  if (decision.kind === "document") showLocalDocument(decision.url);
  else if (decision.kind === "external") parentGate(() => Browser.open({ url: decision.url }), new URL(decision.url).hostname);
  else message("請家長從頁尾開啟資料與授權。" );
}, true);

window.addEventListener("pagehide", () => { if (host.native) host.cancelSpeech(); });
