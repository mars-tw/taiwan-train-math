import { Capacitor, registerPlugin } from "@capacitor/core";
import { App } from "@capacitor/app";
import { Preferences } from "@capacitor/preferences";
import { Browser } from "@capacitor/browser";
import { createNativeStorage, safeExternalUrl } from "../src/native-runtime.js";
import { createAtomicPreferences } from "../src/native-atomic-preferences.js";

const OfflineSpeech = registerPlugin("OfflineSpeech");
const host = window.TrainMathNative = {
  Capacitor, App, native: Capacitor.isNativePlatform(), storage: null,
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
function parentGate(url) {
  let dialog = document.querySelector("#native-parent-gate");
  if (!dialog) {
    dialog = document.createElement("dialog"); dialog.id = "native-parent-gate";
    dialog.setAttribute("aria-labelledby", "native-gate-title");
    dialog.innerHTML = '<form method="dialog" class="dialog-head"><h2 id="native-gate-title">請交給家長</h2><button class="close-btn" aria-label="回到遊戲">×</button></form><p>接下來會離開遊戲，開啟外部資料網站。請家長確認後再繼續。</p><form id="native-gate-form"><label for="native-gate-answer" id="native-gate-question"></label><input id="native-gate-answer" type="text" inputmode="numeric" autocomplete="off"><p id="native-gate-result" role="status"></p><button class="primary-btn" type="submit">家長確認，開啟資料</button></form>';
    document.body.append(dialog);
  }
  const first = 13 + crypto.getRandomValues(new Uint32Array(1))[0] % 17;
  const second = 6 + crypto.getRandomValues(new Uint32Array(1))[0] % 4;
  dialog.querySelector("#native-gate-question").textContent = `請家長計算：${first} × ${second} ＝？`;
  dialog.querySelector("#native-gate-answer").value = "";
  dialog.querySelector("#native-gate-title").textContent = `請交給家長 · ${new URL(url).hostname}`;
  dialog.querySelector("#native-gate-result").textContent = "";
  dialog.querySelector("#native-gate-form").onsubmit = async event => {
    event.preventDefault();
    if (dialog.querySelector("#native-gate-answer").value.trim() !== String(first * second)) {
      dialog.querySelector("#native-gate-result").textContent = "請家長再確認，或關閉回到遊戲。"; return;
    }
    dialog.close(); await host.cancelSpeech();
    try { await Browser.open({ url }); } catch { message("外部資料暫時無法開啟，可以繼續玩。" ); }
  };
  dialog.showModal();
}

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
  const url = new URL(href, location.href);
  const local = new URL(location.href);
  const sameHost = url.protocol === local.protocol && url.host === local.host;
  const documentPath = url.pathname.replace(/^\//, "");
  if (sameHost && Object.hasOwn(window.TrainMathNativeDocuments || {}, documentPath)) {
    event.preventDefault(); event.stopImmediatePropagation(); showLocalDocument(href); return;
  }
  if (sameHost) return;
  event.preventDefault(); event.stopImmediatePropagation();
  const external = safeExternalUrl(href, location.href);
  if (external) { host.cancelSpeech(); parentGate(external); }
  else message("這個連結不適合直接開啟。" );
}, true);

window.addEventListener("pagehide", () => { if (host.native) host.cancelSpeech(); });
