const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

export function photoCreditsMarkup(photo, { native = false, esc = escapeHtml } = {}) {
  if (!photo) return "";
  const attribution = native
    ? `照片：${esc(photo.author)}・${esc(photo.licenseName)}`
    : `照片：${esc(photo.author)}・<a href="${esc(photo.sourceUrl)}" target="_blank" rel="noopener">原始照片 ↗</a>・<a href="${esc(photo.licenseUrl)}" target="_blank" rel="noopener">${esc(photo.licenseName)} ↗</a>`;
  return `<div class="photo-credit"><p>${esc(photo.modelEvidence)}</p><p>${attribution}</p><small>僅下載縮圖供顯示，未修改實車內容。</small></div>`;
}

export function trainSourceLinkMarkup(train, { native = false, esc = escapeHtml } = {}) {
  return native ? "" : `<a href="${esc(train.sources[0])}" target="_blank" rel="noopener">資料來源 ↗</a>`;
}

export function parentResourcesMarkup(trains, learningSources, { verifiedPhoto, esc = escapeHtml } = {}) {
  const link = (url, label) => `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)} ↗</a>`;
  const vehicles = (Array.isArray(trains) ? trains : []).map(train => {
    const photo = verifiedPhoto?.(train);
    const photoLinks = photo ? `<p>照片：${esc(photo.author)}・${esc(photo.licenseName)}</p>${link(photo.sourceUrl, "原始照片")}${link(photo.licenseUrl, "照片授權")}` : "";
    const sources = [...new Set(Array.isArray(train.sources) ? train.sources : [])];
    return `<details><summary>${esc(train.displayName || train.name)}</summary>${photoLinks}${sources.map((url, index) => link(url, `列車資料來源 ${index + 1}`)).join("")}</details>`;
  }).join("");
  const discoveries = Object.values(learningSources || {}).map(source => link(source.url, source.title)).join("");
  return `<section class="native-parent-resources" aria-label="家長資料與授權"><h3>列車照片與資料</h3>${vehicles}<h3>旅途小發現的資料來源</h3>${discoveries}</section>`;
}
