import { createParentChallenge, matchesParentChallenge } from "./native-parent-access.js?v=1.14.0";

// The native host already enforces its own two-stage gate. Web links need a gate too.
export function attachWebParentGate({ native = false } = {}) {
  if (native) return;
  let pending = null;
  const revoke = () => { pending = null; document.querySelector("#web-parent-gate")?.close(); };
  window.addEventListener("pagehide", revoke);
  window.addEventListener("blur", revoke);
  document.addEventListener("visibilitychange", () => { if (document.hidden) revoke(); });
  document.addEventListener("click", event => {
    const link = event.target.closest?.("a[href]");
    const href = link?.getAttribute("href");
    if (!href || href.startsWith("#") || link.hasAttribute("download")) return;
    event.preventDefault(); event.stopImmediatePropagation();
    let url;
    try { url = new URL(href, location.href); } catch { return; }
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) return;
    const challenge = createParentChallenge(values => crypto.getRandomValues(values));
    if (!challenge) return;
    let gate = document.querySelector("#web-parent-gate");
    if (!gate) {
      gate = document.createElement("dialog"); gate.id = "web-parent-gate";
      gate.setAttribute("aria-labelledby", "web-parent-title");
      gate.innerHTML = '<form method="dialog" class="dialog-head"><h2 id="web-parent-title">請交給家長</h2><button class="close-btn" aria-label="回到遊戲">×</button></form><p>這個連結會離開遊戲，請家長確認。</p><form id="web-parent-form"><label for="web-parent-answer" id="web-parent-question"></label><input id="web-parent-answer" inputmode="numeric" autocomplete="off"><p id="web-parent-status" role="status"></p><button type="submit" class="primary-btn">家長確認，開啟連結</button></form>';
      document.body.append(gate); gate.addEventListener("close", () => { pending = null; });
    }
    pending = { challenge, url: url.href };
    gate.querySelector("#web-parent-question").textContent = `請家長計算：${challenge.first} × ${challenge.second} ＝？`;
    gate.querySelector("#web-parent-answer").value = "";
    gate.querySelector("#web-parent-status").textContent = "";
    gate.querySelector("#web-parent-form").onsubmit = event => {
      event.preventDefault();
      if (!pending || !gate.open || document.hidden) return;
      if (!matchesParentChallenge(pending.challenge, gate.querySelector("#web-parent-answer").value)) {
        gate.querySelector("#web-parent-status").textContent = "請家長再確認，或按右上角回到遊戲。"; return;
      }
      const destination = pending.url;
      revoke();
      window.open(destination, "_blank", "noopener,noreferrer");
    };
    gate.showModal();
  }, true);
}
