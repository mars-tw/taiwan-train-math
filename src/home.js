import { LEVELS, GAMES, allowedGames } from "./engine.js?v=1.9.0";
import { storyMarkup } from "./story.js?v=1.9.0";

export const PLAYROOM_CATEGORIES = Object.freeze([
  { id: "math", name: "數學", icon: "123", games: ["count", "boarding", "order", "compare", "pattern", "clock"] },
  { id: "observe", name: "觀察與記憶", icon: "◎", games: ["identify", "memory", "differences", "treasure"] },
  { id: "build", name: "拼搭與方向", icon: "⌁", games: ["puzzle", "tracks", "maze", "program", "mosaic"] },
  { id: "life", name: "生活與分享", icon: "🎟", games: ["cargo", "luggage", "sharing", "balance", "tickets"] },
].map(category => Object.freeze({ ...category, games: Object.freeze([...category.games]) })));

const escapeHtml = value => String(value).replace(/[&<>"']/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[character]);
const escapeFor = esc => typeof esc === "function" ? esc : escapeHtml;
const levelFor = progress => typeof progress?.level === "string" && Object.hasOwn(LEVELS, progress.level) ? progress.level : "small";
function selectedTrain(trains, selected) {
  if (!Array.isArray(trains)) return null;
  return trains.find(train => train?.id === selected) || trains.find(train => train && typeof train.id === "string") || null;
}
function trainName(train) {
  return train?.cardLabel || train?.displayName || train?.name || "陪你出發的列車";
}
function ageButton(level, esc) {
  return `<button type="button" id="quick-settings" class="lobby-age" aria-label="目前 ${esc(LEVELS[level].age)}，開啟家長設定換難度"><strong>${esc(LEVELS[level].age)}</strong><span>換難度 ⚙</span></button>`;
}
function resumeMarkup(resume, level, esc) {
  if (!resume || !Number.isInteger(resume.index) || !Number.isInteger(resume.total) || resume.total < 1 || resume.index < 0 || resume.index >= resume.total) return "";
  const resumeLevel = levelFor({ level: resume.level || resume.meta?.level || level });
  return `<section class="lobby-resume" aria-labelledby="lobby-resume-title"><span class="lobby-resume-icon" aria-hidden="true">🚆</span><div><h2 id="lobby-resume-title">繼續剛剛的旅程</h2><p>${esc(trainName(resume.train))} · ${esc(LEVELS[resumeLevel].age)} · 第 ${resume.index + 1}／${resume.total} 站</p></div><button type="button" id="journey-resume" class="lobby-button lobby-primary">繼續旅程 →</button></section>`;
}

export function homeMarkup({ trains = [], selected, progress, resume = null, esc, image } = {}) {
  const escape = escapeFor(esc), level = levelFor(progress), train = selectedTrain(trains, selected);
  const picture = train && typeof image === "function" ? image(train) : "";
  const preview = train
    ? `<div class="lobby-train">${picture ? `<div class="lobby-train-photo">${picture}</div>` : ""}<div class="lobby-train-copy"><small>今天陪你的列車</small><strong id="selected-name">${escape(trainName(train))}</strong><div class="lobby-train-actions"><button type="button" data-detail="${escape(train.id)}">認識列車 ↗</button><button type="button" data-speak="${escape(train.id)}" aria-label="聽聽${escape(trainName(train))}的名字">♪ 聽名字</button><a href="#collection">換列車 →</a></div></div></div>`
    : '<a class="lobby-choose-train" href="#collection">挑一台喜歡的列車 →</a>';
  return `${storyMarkup()}<div class="lobby-content">${resumeMarkup(resume, level, escape)}<span id="railway-map" class="lobby-anchor" aria-hidden="true"></span><section class="lobby-departure" id="departure" aria-labelledby="lobby-title"><div class="lobby-heading"><div><small>小小列車長</small><h2 id="lobby-title">出發小站</h2><p>一趟 ${LEVELS[level].stops} 站，每站換個任務。</p></div>${ageButton(level, escape)}</div><div class="lobby-start-actions"><button type="button" id="lobby-start" class="lobby-button lobby-primary"><span aria-hidden="true">🚆</span><span><strong><span>驚喜旅程，</span><span>出發！</span></strong><small>讓喜歡的列車帶你玩</small></span><b aria-hidden="true">→</b></button><a class="lobby-button lobby-secondary" href="#playroom">自己選遊戲 →</a></div>${preview}</section></div>`;
}

function routesMarkup({ progress, level, escape, routeMarkup, journeyMarkup }) {
  const provided = routeMarkup ?? journeyMarkup;
  const routes = typeof provided === "function" ? provided({
    level, completed: Array.isArray(progress?.journeysCompleted) ? progress.journeysCompleted : [],
    availableGames: allowedGames(level), esc: escape,
  }) : provided;
  if (typeof routes !== "string" || !routes.trim()) return "";
  // The disclosure owns the old section URL; preserve every route control.
  const content = routes.replace(/\bid=(["'])theme-journeys\1/g, 'id="theme-journeys-routes"');
  return `<details class="playroom-journeys" id="theme-journeys"><summary><span aria-hidden="true">🚆</span><span><strong>六條故事旅程</strong><small>沿途換任務，幫小站完成一件事</small></span><b aria-hidden="true">＋</b></summary><div class="playroom-journey-content">${content}</div></details>`;
}

export function playroomMarkup({ progress, esc, category, routeMarkup, journeyMarkup, trains = [], selected, resume = null } = {}) {
  const escape = escapeFor(esc), level = levelFor(progress), available = new Set(allowedGames(level));
  const active = PLAYROOM_CATEGORIES.some(group => group.id === category) ? category : level === "small" ? "build" : "math";
  const train = selectedTrain(trains, selected);
  const selectedCopy = train
    ? `<div class="playroom-selected-train"><span>陪你出發：<strong>${escape(trainName(train))}</strong></span><a href="#collection">換列車 →</a></div>`
    : '<a class="playroom-select-train" href="#collection">挑一台喜歡的列車 →</a>';
  const tabs = PLAYROOM_CATEGORIES.map(group => `<button type="button" role="tab" id="playroom-tab-${group.id}" data-game-category="${group.id}" aria-selected="${group.id === active}" aria-controls="playroom-panel-${group.id}" tabindex="${group.id === active ? 0 : -1}"><span aria-hidden="true">${escape(group.icon)}</span><strong>${escape(group.name)}</strong></button>`).join("");
  const panels = PLAYROOM_CATEGORIES.map(group => {
    const playable = group.games.filter(id => available.has(id)).length;
    const games = group.games.map(id => {
      const game = GAMES[id], allowed = available.has(id);
      return `<button type="button" class="playroom-game ${allowed ? "" : "playroom-game-later"}" data-mission="${id}" aria-label="${escape(game.name)}${allowed ? "，開始旅程" : "，適合 5–8 歲，查看提示"}"><span class="playroom-game-icon" aria-hidden="true">${escape(game.icon)}</span><span class="playroom-game-copy"><strong>${escape(game.name)}</strong><span>${escape(game.description)}</span><small>${allowed ? "出發玩 →" : "5 歲以上，換難度再玩"}</small></span><b class="playroom-game-arrow" aria-hidden="true">→</b></button>`;
    }).join("");
    return `<section class="playroom-game-panel" id="playroom-panel-${group.id}" role="tabpanel" aria-labelledby="playroom-tab-${group.id}" tabindex="0" ${group.id === active ? "" : "hidden"}><p class="playroom-category-note">${escape(LEVELS[level].age)} · ${playable} 種可以玩</p><div class="playroom-game-list">${games}</div></section>`;
  }).join("");
  return `<section class="playroom-page" id="playroom" aria-labelledby="playroom-title"><header class="playroom-heading"><div><a href="#home" class="playroom-home-link">← 看星光高鐵故事</a><h1 id="playroom-title">遊戲室</h1><p>選一個遊戲，搭喜歡的列車出發。</p></div>${ageButton(level, escape)}</header>${resumeMarkup(resume, level, escape)}${selectedCopy}<div class="playroom-category-tabs" role="tablist" aria-label="遊戲分類">${tabs}</div><p class="playroom-notice" id="home-notice" role="status"></p>${panels}${routesMarkup({ progress, level, escape, routeMarkup, journeyMarkup })}</section>`;
}
