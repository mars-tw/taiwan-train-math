import { railLinks, DIRECTIONS, SOUVENIRS } from "./adventure.js?v=1.2.0";
const treasureIcons = {
  star: { icon: "✦", name: "星星" },
  leaf: { icon: "🍃", name: "葉子" },
  shell: { icon: "🐚", name: "貝殼" },
};
function arrivingTrain(q) {
  const direction = (from, to) =>
    to === from - q.columns
      ? 0
      : to === from + 1
        ? 1
        : to === from + q.columns
          ? 2
          : 3;
  const edges = [
    [0, -50],
    [50, 0],
    [0, 50],
    [-50, 0],
  ];
  let route = "M-15 50 L0 50";
  q.path.forEach((i, at) => {
    const x = (i % q.columns) * 100 + 50,
      y = Math.floor(i / q.columns) * 100 + 50;
    const outgoing =
      at === q.path.length - 1 ? 1 : direction(i, q.path[at + 1]);
    const [dx, dy] = edges[outgoing];
    const exit = `${x + dx - (at === q.path.length - 1 ? 16 : 0)} ${y + dy}`;
    route += q.tiles[i].kind === "curve" ? ` Q${x} ${y} ${exit}` : ` L${exit}`;
  });
  const finishY = Math.floor(q.finish / q.columns) * 100 + 50;
  const train =
    '<rect x="-16" y="-8" width="32" height="16" rx="7" fill="#fffaf0" stroke="#27503b" stroke-width="1.5"/><path d="M-13 5 H9 Q16 5 16 0" fill="none" stroke="#e89b45" stroke-width="3"/><rect x="-7" y="-5" width="12" height="7" rx="2" fill="#396777"/><circle cx="11" cy="-3" r="1.5" fill="#fff0a7"/>';
  return `<svg class="track-vehicle" viewBox="0 0 ${q.columns * 100} ${q.rows * 100}" aria-hidden="true"><g class="rail-arrival-moving"><animateMotion dur="2.4s" repeatCount="1" fill="freeze" rotate="auto" path="${route}"/>${train}</g><g class="rail-arrival-still" transform="translate(${q.columns * 100 - 16} ${finishY})">${train}</g></svg>`;
}
export function railDrawing(kind, rotation, ghost = false) {
  const path = kind === "straight" ? "M50 0 V100" : "M50 0 Q50 50 100 50";
  return `<g transform="rotate(${rotation * 90} 50 50)" ${ghost ? 'class="rail-ghost"' : ""}><path d="${path}" fill="none" stroke="${ghost ? "#cc8b28" : "#536c60"}" stroke-width="20"/><path d="${path}" fill="none" stroke="${ghost ? "#ffe4a3" : "#fff9df"}" stroke-width="12"/><path d="${path}" fill="none" stroke="${ghost ? "#cc8b28" : "#89997d"}" stroke-width="4" ${ghost ? 'stroke-dasharray="5 5"' : ""}/></g>`;
}
export function adventureScene(q, trip) {
  if (q.game === "tracks")
    return `<div class="tracks-stage"><div class="track-signs"><span>🚆 起點 →</span><span>終點小站 🏠</span></div><div class="rail-puzzle ${trip.solved ? "connected" : ""}" style="--columns:${q.columns}">${q.tiles
      .map(
        (tile, i) =>
          `<button class="rail-tile ${tile.kind === "empty" ? "scenery-tile" : ""} ${i === q.start ? "rail-start" : ""} ${i === q.finish ? "rail-finish" : ""}" data-rotate="${i}" ${tile.kind === "empty" || trip.solved ? "disabled" : ""} aria-label="第 ${i + 1} 格${
            tile.kind === "empty"
              ? "，草地"
              : `，${tile.kind === "curve" ? "彎" : "直"}軌道，接往${railLinks(
                  tile.kind,
                  trip.rotations[i],
                )
                  .map((d) => DIRECTIONS[d])
                  .join("和")}，點一下轉向`
          }">${tile.kind === "empty" ? '<span aria-hidden="true">🌳</span>' : `<svg viewBox="0 0 100 100" aria-hidden="true">${trip.trackHint ? railDrawing(tile.kind, tile.solution, true) : ""}${railDrawing(tile.kind, trip.rotations[i])}</svg>`}${i === q.start ? '<i class="track-endpoint" aria-hidden="true">起</i>' : i === q.finish ? '<i class="track-endpoint" aria-hidden="true">站</i>' : ""}</button>`,
      )
      .join(
        "",
      )}${trip.solved ? arrivingTrain(q) : ""}</div>${trip.solved ? '<div class="track-arrival"><span aria-hidden="true">🚄</span><strong>路接通了，列車到站！</strong></div>' : '<p class="track-instruction">每點一下，軌道轉四分之一圈。從「起」跟著走到「站」。</p>'}<div class="adventure-actions"><button class="text-btn" id="tracks-reset" ${trip.solved ? "disabled" : ""}>重新鋪一次</button><button class="primary-btn" id="tracks-submit" ${trip.solved ? "disabled" : ""}>讓列車出發 →</button></div></div>`;
  if (q.game === "sharing") {
    const left = q.total - trip.shares.reduce((a, b) => a + b, 0);
    return `<div class="sharing-stage"><div class="picnic-basket"><span class="stage-label">列車點心籃 · 還有 ${left} 份</span><div>${Array.from({ length: left }, () => `<span aria-hidden="true">${q.food}</span>`).join("") || "<strong>點心都分好了，看看每位是否一樣多。</strong>"}</div></div><div class="picnic-friends" style="--friends:${q.friends}">${trip.shares.map((n, i) => `<div class="picnic-friend"><span class="friend-face" aria-hidden="true">${["🐻", "🐰", "🐼"][i]}</span><strong>${["小熊", "小兔", "小貓熊"][i]} · ${n} 份</strong><div class="picnic-plate">${Array.from({ length: n }, (_, j) => `<button data-return-snack="${i}" ${trip.solved ? "disabled" : ""} aria-label="從${["小熊", "小兔", "小貓熊"][i]}搬回第 ${j + 1} 份點心">${q.food}</button>`).join("") || "<span>小盤子</span>"}</div><button class="secondary-btn" data-share="${i}" ${left === 0 || trip.solved ? "disabled" : ""}>給${["小熊", "小兔", "小貓熊"][i]} 1 份</button></div>`).join("")}</div><div class="adventure-actions"><button id="sharing-reset" class="text-btn" ${trip.solved ? "disabled" : ""}>全部放回籃子</button><button id="sharing-submit" class="primary-btn" ${trip.solved ? "disabled" : ""}>大家一樣多了 ✓</button></div></div>`;
  }
  if (q.game === "treasure") {
    const found = trip.found.size;
    return `<div class="treasure-stage"><div class="treasure-toolbar"><span>尋找 <b>${treasureIcons[q.target].icon} ${treasureIcons[q.target].name}</b></span><strong>已找到 ${found} / ${q.answer}</strong></div><div class="treasure-landscape ${trip.solved ? "treasure-complete" : ""}" style="--treasure-columns:${q.items.length === 9 ? 3 : 4}"><img src="assets/images/railway-world-v2.webp" alt="想像鐵道樂園尋寶風景" width="1672" height="941" loading="lazy"><div class="treasure-items">${q.items.map((kind, i) => `<button class="treasure-item kind-${kind} ${trip.found.has(i) ? "found" : ""} ${trip.treasureHint && kind === q.target ? "treasure-highlight" : ""}" data-find="${i}" ${trip.solved || trip.found.has(i) ? "disabled" : ""} aria-label="第 ${i + 1} 個，${treasureIcons[kind].name}${trip.found.has(i) ? "，已找到" : ""}"><span aria-hidden="true">${treasureIcons[kind].icon}</span>${trip.found.has(i) ? '<i aria-hidden="true">✓</i>' : ""}</button>`).join("")}</div>${trip.solved ? '<div class="treasure-message"><span aria-hidden="true">✉ ✦</span><strong>寶物都找到了！</strong></div>' : ""}</div><p class="treasure-help">找到的會留下亮亮記號，慢慢找就好。</p></div>`;
  }
  return "";
}
export function souvenirMarkup(trip) {
  if (!trip.gift)
    return '<div class="souvenir-envelope"><span aria-hidden="true">✉ ✦</span><h2>旅途的小禮物，到了！</h2><p>打開看看，這趟旅行留下什麼新發現。</p><button id="gift-open" class="primary-btn">打開紀念信封 →</button><small>每趟一份，免費收藏；所有遊戲都能直接玩。</small></div>';
  return `<div class="souvenir-envelope gift-opened" role="status"><span aria-hidden="true">${trip.gift.icon}</span><small>這趟的旅途小禮物</small><h2>${trip.gift.name}</h2><p>${trip.gift.story}</p><a href="#stamps" class="text-link">已放進鐵道護照 · 去看看 →</a></div>`;
}
export function souvenirCollection(progress) {
  const items = progress.souvenirs
    .map((id) => SOUVENIRS.find((item) => item.id === id))
    .filter(Boolean);
  return `<section class="souvenir-collection" aria-labelledby="souvenir-title"><h2 id="souvenir-title">旅途小禮物</h2><p>每趟旅程的小發現，收在這裡。已收藏 ${items.length} 款。</p>${items.length ? `<div class="souvenir-grid">${items.map((item) => `<article><span aria-hidden="true">${item.icon}</span><strong>${item.name}</strong><p>${item.story}</p></article>`).join("")}</div>` : "<p>完成旅程後，試試打開紀念信封吧。</p>"}</section>`;
}
