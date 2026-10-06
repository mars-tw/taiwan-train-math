// Native policy and bridge coordination only. Game state stays in app.js and
// continues to pass the existing progress/session validators.
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const MAX_VALUE_LENGTH = 131072;

function dataOptions(value, names) {
  try {
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) return null;
    const descriptors = Object.getOwnPropertyDescriptors(value);
    if (Reflect.ownKeys(descriptors).some(key => typeof key !== "string" || !names.includes(key) || !own(descriptors[key], "value"))) return null;
    const result = Object.create(null);
    for (const name of names) if (own(descriptors, name)) result[name] = descriptors[name].value;
    return result;
  } catch { return null; }
}

export function isNativeHost(host) {
  try {
    const capacitor = host?.Capacitor || host;
    return typeof capacitor?.isNativePlatform === "function"
      && typeof capacitor.getPlatform === "function"
      && capacitor.isNativePlatform() === true
      && ["android", "ios"].includes(capacitor.getPlatform());
  } catch { return false; }
}

export function backAction(options = {}) {
  const state = dataOptions(options, ["dialogOpen", "storyMenuOpen", "view"]);
  if (!state) return "minimize";
  if (state.dialogOpen === true) return "close-dialog";
  if (state.storyMenuOpen === true) return "close-story";
  if (state.view === "game") return "pause-trip";
  if (["playroom", "collection", "stamps", "finish"].includes(state.view)) return "go-home";
  return "minimize";
}

export function safeExternalUrl(href, base) {
  try {
    if (typeof href !== "string" || typeof base !== "string" || !/^https:\/\//i.test(href.trim())
      || /^https:\/\/[^/?#]*@/i.test(href.trim())
      || href.length > 4096 || /[\u0000-\u001f\u007f]/.test(href)) return null;
    const origin = new URL(base);
    const url = new URL(href.trim(), origin);
    const hostname = url.hostname.toLowerCase().replace(/\.+$/, "");
    if (url.protocol !== "https:" || url.username || url.password || url.origin === origin.origin
      || hostname === "localhost" || hostname.endsWith(".localhost")
      || hostname === "0.0.0.0" || /^127\./.test(hostname)
      || ["[::1]", "[::]"].includes(hostname) || /^\[::ffff:7f[0-9a-f]{2}:[0-9a-f]+\]$/.test(hostname)) return null;
    return url.href;
  } catch { return null; }
}

function validKeys(value) {
  try {
    if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype
      || value.length < 1 || value.length > 16) return false;
    const descriptors = Object.getOwnPropertyDescriptors(value);
    if (Reflect.ownKeys(descriptors).some(key => typeof key !== "string" || (key !== "length" && !/^(?:0|[1-9]\d*)$/.test(key)))) return false;
    const keys = [];
    for (let index = 0; index < value.length; index++) {
      const descriptor = descriptors[index];
      if (!descriptor || !own(descriptor, "value")) return false;
      const key = descriptor.value;
      if (typeof key !== "string" || !/^[a-zA-Z0-9_.-]{1,128}$/.test(key)
        || ["__proto__", "constructor", "prototype"].includes(key)) return false;
      keys.push(key);
    }
    return new Set(keys).size === keys.length;
  } catch { return false; }
}

export async function createNativeStorage(preferences, options = {}) {
  const configuration = dataOptions(options, ["keys", "onError"]);
  const keys = configuration && validKeys(configuration.keys) ? [...configuration.keys] : [];
  const onError = typeof configuration?.onError === "function" ? configuration.onError : null;
  const allowed = new Set(keys), memory = new Map(), blocked = new Set();
  let error = null, queue = Promise.resolve(), get, set, remove, setMany;
  const report = (operation, key = null) => {
    const failure = Object.freeze({ operation, key });
    error ||= failure;
    try { onError?.(failure); } catch {}
  };
  const validKey = key => typeof key === "string" && allowed.has(key);
  const demandKey = key => {
    if (validKey(key)) return;
    report("key");
    throw new TypeError("Unknown native storage key");
  };
  const enqueue = (operation, key, value) => {
    const result = queue.then(async () => {
      try {
        if (operation === "set") await set({ key, value });
        else if (operation === "commit") await setMany({ values: value });
        else await remove({ key });
        return true;
      } catch { report(operation, key); return false; }
    });
    queue = result.then(() => {});
    return result;
  };
  try {
    const methods = [preferences?.get, preferences?.set, preferences?.remove];
    if (!keys.length || methods.some(method => typeof method !== "function")) {
      report("config");
      keys.forEach(key => blocked.add(key));
      get = set = remove = null;
    } else {
      [get, set, remove] = methods.map(method => Function.prototype.bind.call(method, preferences));
      const transaction = preferences?.setMany;
      if (typeof transaction === "function") setMany = Function.prototype.bind.call(transaction, preferences);
    }
  } catch { report("config"); keys.forEach(key => blocked.add(key)); get = set = remove = null; }

  if (get) await Promise.all(keys.map(async key => {
    try {
      const response = dataOptions(await get({ key }), ["value"]);
      if (!response || !own(response, "value") || (response.value !== null
        && (typeof response.value !== "string" || response.value.length > MAX_VALUE_LENGTH))) {
        blocked.add(key); report("hydrate", key); return;
      }
      if (response.value !== null) memory.set(key, response.value);
    } catch { blocked.add(key); report("hydrate", key); }
  }));

  return Object.freeze({
    get error() { return error; },
    getItem(key) {
      if (!validKey(key)) { report("key"); return null; }
      return memory.has(key) ? memory.get(key) : null;
    },
    setItem(key, value) {
      demandKey(key);
      if (typeof value !== "string" || value.length > MAX_VALUE_LENGTH) {
        report("set", key); throw new TypeError("Invalid native storage value or bridge");
      }
      memory.set(key, value);
      // A failed read is not proof that the key is empty. Keep current-session
      // work in memory, but never overwrite an unread native record with it.
      if (blocked.has(key) || !set) {
        report("set", key); throw new TypeError("Native storage key was not readable");
      }
      enqueue("set", key, value);
    },
    removeItem(key) {
      demandKey(key);
      memory.delete(key);
      if (blocked.has(key) || !remove) {
        report("remove", key); throw new TypeError("Native storage key was not readable");
      }
      enqueue("remove", key);
    },
    commit(values) {
      const changes = dataOptions(values, keys);
      if (!changes || !Object.keys(changes).length || !Object.values(changes).every(value => value === null
        || (typeof value === "string" && value.length <= MAX_VALUE_LENGTH))) {
        report("commit"); throw new TypeError("Invalid native storage transaction");
      }
      for (const key of Object.keys(changes)) {
        if (changes[key] === null) memory.delete(key);
        else memory.set(key, changes[key]);
      }
      const unread = Object.keys(changes).find(key => blocked.has(key));
      if (unread || !setMany) {
        report("commit", unread || null); throw new TypeError("Native storage transaction unavailable");
      }
      return enqueue("commit", null, Object.freeze(changes));
    },
    async flush() {
      // Include writes queued while an earlier awaited write was completing.
      let pending;
      do { pending = queue; await pending; } while (pending !== queue);
      return error === null;
    },
  });
}

export async function attachNativeLifecycle(appPlugin, options = {}) {
  const callbacks = dataOptions(options, ["onPause", "onBack"]);
  const handles = [];
  let closed = false, inactive = false, cleanupPromise = null, attached = true;
  const invoke = callback => {
    if (typeof callback !== "function") return;
    try { Promise.resolve(callback()).catch(() => {}); } catch {}
  };
  const cleanup = () => cleanupPromise ||= (async () => {
    closed = true;
    let removed = attached;
    for (const handle of handles) {
      try { await handle.remove(); } catch { removed = false; }
    }
    return removed;
  })();
  try {
    // A back listener overrides Android's default behaviour. Never install an
    // inert one if the caller has not supplied its full lifecycle callbacks.
    if (!callbacks || typeof callbacks.onPause !== "function" || typeof callbacks.onBack !== "function"
      || typeof appPlugin?.addListener !== "function") { attached = false; return cleanup; }
    const stateChange = event => {
      if (closed) return;
      const state = dataOptions(event, ["isActive"]);
      if (!state || typeof state.isActive !== "boolean") return;
      if (state.isActive) { inactive = false; return; }
      if (inactive) return;
      inactive = true;
      invoke(callbacks.onPause);
    };
    const back = () => { if (!closed) invoke(callbacks.onBack); };
    for (const [name, callback] of [["appStateChange", stateChange], ["backButton", back]]) {
      const handle = await appPlugin.addListener(name, callback);
      if (typeof handle?.remove !== "function") throw new TypeError("Invalid native listener handle");
      handles.push(handle);
    }
  } catch { attached = false; await cleanup(); }
  return cleanup;
}
