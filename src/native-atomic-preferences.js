// One physical Preferences value holds the logical passport/snapshot pair.
// Each operation is atomic; callers use setMany for a whole finish transaction.
const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
const MAX_VALUE_LENGTH = 131072;
const MAX_ENVELOPE_LENGTH = MAX_VALUE_LENGTH * 12 + 2048;

function dataRecord(value, names) {
  try {
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) return null;
    const descriptors = Object.getOwnPropertyDescriptors(value), result = Object.create(null);
    for (const key of Reflect.ownKeys(descriptors)) {
      if (typeof key !== "string" || !names.includes(key) || !own(descriptors[key], "value")) return null;
      result[key] = descriptors[key].value;
    }
    return result;
  } catch { return null; }
}
const keyValid = key => typeof key === "string" && /^[a-zA-Z0-9_.-]{1,128}$/.test(key)
  && !["__proto__", "constructor", "prototype"].includes(key);
function pairValid(keys) {
  try {
    return Array.isArray(keys) && Object.getPrototypeOf(keys) === Array.prototype && keys.length === 2
      && Reflect.ownKeys(keys).every(key => ["0", "1", "length"].includes(key))
      && [0, 1].every(index => own(Object.getOwnPropertyDescriptor(keys, index) || {}, "value") && keyValid(keys[index]))
      && keys[0] !== keys[1];
  } catch { return false; }
}
const valueValid = value => value === null || (typeof value === "string" && value.length <= MAX_VALUE_LENGTH);
function responseValue(response) {
  const result = dataRecord(response, ["value"]);
  if (!result || !own(result, "value") || (result.value !== null && typeof result.value !== "string"))
    throw new TypeError("Invalid native preference response");
  return result.value;
}

export async function createAtomicPreferences(preferences, options = {}) {
  const configuration = dataRecord(options, ["keys", "storageKey"]);
  const keys = configuration && pairValid(configuration.keys) ? [...configuration.keys] : [];
  const storageKey = configuration?.storageKey;
  const values = new Map(keys.map(key => [key, null]));
  let get, set, locked = false, error = null, queue = Promise.resolve();
  const fail = operation => { error ||= Object.freeze({ operation, key: keyValid(storageKey) ? storageKey : null }); };
  try {
    const methods = [preferences?.get, preferences?.set];
    if (keys.length !== 2 || !keyValid(storageKey) || keys.includes(storageKey) || methods.some(method => typeof method !== "function"))
      throw new TypeError("Invalid atomic storage configuration");
    [get, set] = methods.map(method => Function.prototype.bind.call(method, preferences));
  } catch { locked = true; fail("config"); }

  if (!locked) {
    try {
      const stored = responseValue(await get({ key: storageKey }));
      if (stored === null) {
        // Read migration candidates only. The old keys are never changed or
        // deleted, and nothing is persisted until a legitimate new operation.
        const legacy = await Promise.all(keys.map(async key => responseValue(await get({ key }))));
        if (!legacy.every(valueValid)) throw new TypeError("Invalid legacy preference value");
        keys.forEach((key, index) => values.set(key, legacy[index]));
      } else {
        if (stored.length > MAX_ENVELOPE_LENGTH) throw new TypeError("Oversized native envelope");
        const envelope = dataRecord(JSON.parse(stored), ["version", "values"]);
        const content = dataRecord(envelope?.values, keys);
        if (!envelope || envelope.version !== 1 || !content || !keys.every(key => own(content, key) && valueValid(content[key])))
          throw new TypeError("Invalid native envelope");
        keys.forEach(key => values.set(key, content[key]));
      }
    } catch { locked = true; fail("hydrate"); }
  }

  const demand = () => { if (locked) throw new TypeError("Atomic native preferences were not readable"); };
  const demandKey = key => { if (typeof key !== "string" || !keys.includes(key)) throw new TypeError("Unknown logical native key"); };
  const write = () => {
    const payload = JSON.stringify({ version: 1, values: Object.fromEntries(keys.map(key => [key, values.get(key)])) });
    const result = queue.then(async () => {
      try { await set({ key: storageKey, value: payload }); }
      catch { fail("write"); throw new TypeError("Atomic native preferences could not be saved"); }
    });
    // A failed submission does not prevent later operations recovering the
    // complete intended pair, including any already-staged logical deletion.
    queue = result.catch(() => {});
    return result;
  };

  return Object.freeze({
    get error() { return error; },
    async get(options) {
      demand(); const request = dataRecord(options, ["key"]); demandKey(request?.key);
      return { value: values.get(request.key) };
    },
    async set(options) {
      demand(); const request = dataRecord(options, ["key", "value"]); demandKey(request?.key);
      if (typeof request.value !== "string" || !valueValid(request.value)) throw new TypeError("Invalid logical preference value");
      values.set(request.key, request.value);
      await write();
    },
    async remove(options) {
      demand(); const request = dataRecord(options, ["key"]); demandKey(request?.key);
      values.set(request.key, null);
      await write();
    },
    async setMany(options) {
      demand(); const request = dataRecord(options, ["values"]), changes = dataRecord(request?.values, keys);
      if (!changes || !Object.keys(changes).length || !Object.values(changes).every(valueValid))
        throw new TypeError("Invalid logical preference transaction");
      for (const key of Object.keys(changes)) values.set(key, changes[key]);
      await write();
    },
  });
}
