const LOCAL_IMAGE = /^assets\/images\/[a-zA-Z0-9_-]+\.(?:webp|png|jpe?g|avif)$/;
// A retry uses a new URL, while question recipes retain their original asset.
export function createPhotoLoader({ makeImage = () => new Image(), onChange = () => {}, timeoutMs = 15000,
  schedule = setTimeout, cancel = clearTimeout } = {}) {
  const entries = new Map();
  let attempt = 0;
  const basePath = source => String(source).split("?")[0];
  function begin(path, retry = false) {
    if (!LOCAL_IMAGE.test(path)) return;
    const entry = { status: "loading", source: retry ? `${path}?photo-retry=${Date.now()}-${++attempt}` : path };
    entries.set(path, entry);
    const picture = makeImage();
    let timer;
    const settle = status => {
      if (timer !== undefined) cancel(timer);
      if (entries.get(path) !== entry || entry.status === status) return;
      entry.status = status;
      onChange(path);
    };
    picture.onload = () => settle(picture.naturalWidth > 0 ? "ready" : "error");
    picture.onerror = () => settle("error");
    timer = schedule(() => settle("error"), timeoutMs);
    picture.src = entry.source;
  }
  return {
    status(paths) {
      const unique = [...new Set(paths)];
      for (const path of unique) if (LOCAL_IMAGE.test(path) && !entries.has(path)) begin(path);
      if (unique.some(path => !LOCAL_IMAGE.test(path) || entries.get(path)?.status === "error")) return "error";
      return unique.some(path => entries.get(path)?.status !== "ready") ? "loading" : "ready";
    },
    source(path) { return entries.get(path)?.source || path; },
    retry(paths) { for (const path of new Set(paths)) begin(path, true); },
    report(source, status) {
      const path = basePath(source);
      if (!LOCAL_IMAGE.test(path) || !["error", "ready"].includes(status)) return;
      const existing = entries.get(path);
      if (existing && existing.source !== source) return;
      if (existing?.status === status) return;
      entries.set(path, { source, status });
      onChange(path);
    },
  };
}
