import { safeExternalUrl } from "./native-runtime.js";

// A gate failure (including an unavailable random source) never grants access.
export function createParentChallenge(getRandomValues) {
  try {
    if (typeof getRandomValues !== "function") return null;
    const numbers = new Uint32Array(2);
    if (getRandomValues(numbers) !== numbers) return null;
    return Object.freeze({ first: 13 + numbers[0] % 17, second: 6 + numbers[1] % 4 });
  } catch { return null; }
}

export function matchesParentChallenge(challenge, answer) {
  return Number.isInteger(challenge?.first) && Number.isInteger(challenge?.second)
    && challenge.first >= 13 && challenge.first <= 29
    && challenge.second >= 6 && challenge.second <= 9
    && typeof answer === "string" && answer.trim() === String(challenge.first * challenge.second);
}

export function classifyNativeResourceLink(href, base, documents, { authorized = false, inParentArea = false } = {}) {
  if (!authorized || !inParentArea || typeof href !== "string" || !href || href.startsWith("#")) return { kind: "blocked" };
  try {
    const url = new URL(href, base), local = new URL(base);
    if (url.protocol === local.protocol && url.host === local.host) {
      const path = url.pathname.replace(/^\//, "");
      return documents && Object.hasOwn(documents, path) ? { kind: "document", url: href } : { kind: "blocked" };
    }
    const external = safeExternalUrl(href, base);
    return external ? { kind: "external", url: external } : { kind: "blocked" };
  } catch { return { kind: "blocked" }; }
}
