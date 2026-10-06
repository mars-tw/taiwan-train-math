import {
  LEVELS,
  createTrip,
  isCorrect,
  readProgress,
  saveProgress,
  defaults,
  STORAGE_KEY,
  GAMES,
  allowedGames,
  clockLabel,
  newMemoryState,
  memoryTurn,
  rememberTrip,
  seededRandom,
} from "./engine.js?v=1.10.1";
import { arithmeticScene, parseArithmeticAnswer } from "./arithmetic-ui.js?v=1.10.1";
import { homeMarkup, playroomMarkup, starterPractice } from "./home.js?v=1.10.1";
import { countingScene, discoveryMarkup } from "./learning-ui.js?v=1.10.1";
import { learningGuide } from "./learning-guide.js?v=1.10.1";
import { learningDiscovery } from "./learning-content.js?v=1.10.1";
import {
  activityScene,
  patternToken,
  patternName,
} from "./activities.js?v=1.10.1";
import { mountStory, newStoryState } from "./story.js?v=1.10.1";
import {
  newAdventureState,
  trackConnected,
  changeShare,
  SOUVENIRS,
} from "./adventure.js?v=1.10.1";
import {
  adventureScene,
  souvenirMarkup,
  souvenirCollection,
  giftDetailMarkup,
} from "./adventure-ui.js?v=1.10.1";
import { newPuzzleState, selectPuzzlePiece, placePuzzlePiece, puzzleScene } from "./puzzle.js?v=1.10.1";
import { newExplorerState, selectLuggage, putLuggage, moveMaze, explorerScene } from "./explorers.js?v=1.10.1";
import { enqueueGift, offerGifts, claimGift } from "./rewards.js?v=1.10.1";
import { attachPuzzleTouch } from "./puzzle-touch.js?v=1.10.1";
import { saveTripSession, readTripSession, clearTripSession } from "./trip-session.js?v=1.10.1";
import { newWorkshopState, appendCommand, removeCommand, evaluateProgram, addWeight, removeWeight, weightTotal, workshopScene } from "./workshop.js?v=1.10.1";
import { newDiscoveryState, selectMosaicColor, paintMosaicCell, resetMosaic, findDifference, discoveryScene } from "./discovery.js?v=1.10.1";
import { JOURNEYS, journeyById, journeyMarkup } from "./journeys.js?v=1.10.1";
import { displayTrain, trainImage, verifiedPhoto, photoLabel, photoGameTrains, samePhotoIdentity } from "./train-images.js?v=1.10.1";
import { newTicketsState, selectTicket, payToken, returnToken, ticketTotals, ticketsScene } from "./tickets.js?v=1.10.1";
import { createPhotoLoader } from "./photo-loader.js?v=1.10.1";
import { createProgramPlayback } from "./program-playback.js?v=1.10.1";
import { resolvePage } from "./navigation.js?v=1.10.1";

const main = document.querySelector("#main");
const esc = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const $ = (selector) => document.querySelector(selector);
const storySession = newStoryState();
const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
let storyHandle = null;
function stopStory() {
  storyHandle?.destroy();
  storyHandle = null;
}
let catalogue,
  trains = [],
  progress,
  trip = null,
  view = "home",
  filter = "all",
  search = "",
  selected = "700t",
  practice = "mixed",
  selectedJourney = null,
  playroomCategory = null,
  mood = "golden",
  departureToken = null,
  audioContext;
let observedDock = null;
const gameDockObserver = typeof ResizeObserver === "function" ? new ResizeObserver(updateDockSpace) : null;
function updateDockSpace() {
  if (!observedDock?.isConnected || view !== "game") return;
  const fixed = getComputedStyle(observedDock).position === "fixed";
  document.documentElement.style.setProperty("--game-dock-height", `${fixed ? observedDock.offsetHeight + 12 : 0}px`);
}
function watchGameDock() {
  gameDockObserver?.disconnect();
  observedDock = document.querySelector("#game-actions");
  if (observedDock) gameDockObserver?.observe(observedDock);
  updateDockSpace();
}
function revealFeedback() {
  const feedback = document.querySelector(".feedback");
  if (!feedback?.textContent.trim()) return;
  const rect = feedback.getBoundingClientRect();
  if (rect.top < 0 || rect.bottom > window.innerHeight)
    feedback.scrollIntoView({ block: "nearest", behavior: "instant" });
}
function stopGameDock() {
  gameDockObserver?.disconnect(); observedDock = null;
  document.documentElement.style.removeProperty("--game-dock-height");
}
let pausedTrip = null, pointerInteraction = false, tripSaveWarning = false;
let questionScroll = { key: null, positions: {} };
let activeProgramRun = null;
const programPlayer = createProgramPlayback({ delay: () => progress?.reduceMotion || motionPreference.matches ? 0 : 420 });
let activePhotoTask = null, photoRenderRequest = null;
const photoLoader = createPhotoLoader({ onChange(path) {
  if (view !== "game" || !trip || trip.awarded || !activePhotoTask?.paths.includes(path)) return;
  if (photoLoader.status(activePhotoTask.paths) === activePhotoTask.status) return;
  if (photoRenderRequest) cancelAnimationFrame(photoRenderRequest.id);
  const request = { trip, index: trip.index, key: activePhotoTask.key };
  photoRenderRequest = request;
  request.id = requestAnimationFrame(() => {
    if (photoRenderRequest !== request) return;
    photoRenderRequest = null;
    if (trip === request.trip && !trip.awarded && view === "game" && trip.index === request.index && activePhotoTask?.key === request.key) renderQuestion();
  });
} });
function clearPhotoTask() {
  if (photoRenderRequest) cancelAnimationFrame(photoRenderRequest.id);
  photoRenderRequest = null;
  activePhotoTask = null;
}
let tripStorage;
try { tripStorage = sessionStorage; } catch { tripStorage = null; }
const touchDevice = () => window.matchMedia("(pointer: coarse)").matches || navigator.maxTouchPoints > 0;
document.addEventListener("pointerdown", () => {
  pointerInteraction = true;
  unlockAudio();
}, { capture: true, passive: true });
document.addEventListener("keydown", () => { pointerInteraction = false; }, true);
const labels = {
  tra: "台鐵列車",
  thsr: "台灣高鐵",
  forest: "阿里山林鐵",
  tourism: "觀光列車",
  bullet: "子彈列車",
  maglev: "磁浮列車",
  heritage: "經典列車",
};
const gameLabels = Object.fromEntries(
  Object.entries(GAMES).map(([id, game]) => [id, game.name]),
);
const gameIcons = Object.fromEntries(
  Object.entries(GAMES).map(([id, game]) => [id, game.icon]),
);
const stationNames = {
  count: "數數月台", identify: "認車車庫", boarding: "加減小站",
  order: "編組站", compare: "車票站", pattern: "規律站",
  cargo: "貨運站", memory: "記憶車庫", clock: "鐘樓站",
  tracks: "工程站", sharing: "點心站", treasure: "尋寶站",
  puzzle: "拼圖小站", luggage: "行李站", maze: "迷宮站",
  program: "指令教室", balance: "秤重站", mosaic: "圖形工坊", differences: "觀察月台",
  tickets: "售票小站",
};
const byId = (id) => trains.find((t) => t.id === id);
let storage;
try {
  storage = localStorage;
} catch {
  storage = { getItem: () => null, setItem: () => { throw new Error("Storage unavailable"); }, removeItem: () => {} };
}
progress = readProgress(storage);
function persist() {
  if (!saveProgress(storage, progress))
    announce("這台裝置無法儲存進度，但還是可以繼續玩。");
}
function saveCurrentTrip() {
  const current = trip && !trip.awarded ? trip : pausedTrip;
  if (!current) return;
  const saved = saveTripSession(tripStorage, current);
  if (!saved && !tripSaveWarning) announce("這台裝置無法暫存旅程，仍可繼續玩；重新整理後可能要重新開始。");
  tripSaveWarning = !saved;
}
function pauseTrip() {
  stopProgramRun();
  if (trip && !trip.awarded) {
    pausedTrip = trip;
    saveCurrentTrip();
  }
}
function resumeJourney() {
  stopProgramRun();
  if (!pausedTrip) return;
  stopStory();
  clearDeparture();
  cancelVoice();
  clearPhotoTask();
  trip = pausedTrip;
  pausedTrip = null;
  view = "game";
  selected = trip.train.id;
  practice = trip.meta.practice;
  selectedJourney = trip.meta.journey;
  renderQuestion();
  window.scrollTo({ top: 0, behavior: "instant" });
  announce("回到剛剛的旅程了，繼續慢慢玩吧。");
}
function unlockAudio() {
  if (!progress?.effects) return;
  try {
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return;
    audioContext ||= new Context();
    if (audioContext.state === "suspended") audioContext.resume().catch(() => {});
  } catch {}
}
function fullscreenButton() {
  const supported = document.fullscreenEnabled || document.documentElement.webkitRequestFullscreen;
  return supported ? '<button id="game-fullscreen" class="icon-btn" aria-label="放大遊戲畫面" aria-pressed="false">⛶</button>' : "";
}
async function toggleGameFullscreen() {
  try {
    const active = document.fullscreenElement || document.webkitFullscreenElement;
    if (active) await (document.exitFullscreen?.() || document.webkitExitFullscreen?.());
    else await (document.documentElement.requestFullscreen?.() || document.documentElement.webkitRequestFullscreen?.());
  } catch { announce("這台裝置沒有開啟全螢幕，還是可以繼續玩。"); }
}
function announce(text) {
  $("#announcement").textContent = text;
}
function applyPreferences() {
  document.body.classList.toggle("reduced-motion", progress.reduceMotion);
  $("#sound-toggle").textContent = progress.voice ? "♫" : "♪";
  $("#sound-toggle").setAttribute(
    "aria-label",
    progress.voice ? "關閉語音" : "開啟語音",
  );
  $("#sound-toggle").setAttribute("aria-pressed", String(progress.voice));
  if ($("#station-bell")) $("#station-bell").disabled = !progress.effects;
  storyHandle?.setReduced(progress.reduceMotion || motionPreference.matches);
}
function speak(text, force = false) {
  if (!("speechSynthesis" in window) || (!progress.voice && !force)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(
    text.replace(/TEMU/gi, "T，E，M，U，").replace(/EMU/gi, "E，M，U，"),
  );
  u.lang = "zh-TW";
  u.rate = 0.82;
  const voices = window.speechSynthesis.getVoices();
  u.voice =
    voices.find((v) => v.lang.toLowerCase() === "zh-tw") ||
    voices.find((v) => v.lang.startsWith("zh")) ||
    null;
  window.speechSynthesis.speak(u);
}
function cancelVoice() {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}
async function chime() {
  if (!progress.effects) return;
  try {
    audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
    await audioContext.resume();
    if (!progress.effects || document.hidden) return;
    [523.25, 659.25, 783.99].forEach((frequency, i) => {
      const o = audioContext.createOscillator(),
        g = audioContext.createGain();
      o.type = "sine";
      o.frequency.value = frequency;
      g.gain.setValueAtTime(0, audioContext.currentTime + i * 0.12);
      g.gain.linearRampToValueAtTime(
        0.055,
        audioContext.currentTime + i * 0.12 + 0.025,
      );
      g.gain.exponentialRampToValueAtTime(
        0.001,
        audioContext.currentTime + i * 0.12 + 0.3,
      );
      o.connect(g).connect(audioContext.destination);
      o.start(audioContext.currentTime + i * 0.12);
      o.stop(audioContext.currentTime + i * 0.12 + 0.32);
    });
  } catch {}
}
function image(t, cls = "", lazy = true, contentVersion = "1.8.0") {
  const original = trainImage(t, contentVersion), src = original ? photoLoader.source(original) : null;
  const real = ["1.7.0", "1.8.0"].includes(contentVersion);
  if (!src) return `<span class="photo-pending ${cls}" role="img" aria-label="${esc(displayTrain(t).name)}的實車照片待補"><span aria-hidden="true">▧</span><small>實車照片待補</small></span>`;
  return `<img class="${cls} ${real ? "real-train-photo" : ""}" src="${esc(src)}" alt="${esc(displayTrain(t).name)}的${real ? photoLabel(t) : "想像情境插圖"}" ${lazy ? 'loading="lazy"' : 'fetchpriority="high"'} width="1200" height="675">`;
}
const gameImage = (t, cls = "", lazy = true) => image(t, cls, lazy, trip.meta.contentVersion);
const gameById = id => ["1.7.0", "1.8.0"].includes(trip.meta.contentVersion) ? displayTrain(byId(id)) : byId(id);
function tag(t) {
  return `<span class="tag ${t.category}">${esc(t.tag || labels[t.category])}</span>`;
}
function artNote(t) {
  const p = verifiedPhoto(t);
  return `${photoLabel(t)}${p ? `・${esc(p.author)}` : ""}`;
}
function photoCredits(t) {
  const p = verifiedPhoto(t);
  if (!p) return `<p class="photo-credit">${esc(t.referencePhoto?.reason || "還在尋找可確認型號及授權的實車照片。")}</p>`;
  return `<div class="photo-credit"><p>${esc(p.modelEvidence)}</p><p>照片：${esc(p.author)}・<a href="${esc(p.sourceUrl)}" target="_blank" rel="noopener">原始照片 ↗</a>・<a href="${esc(p.licenseUrl)}" target="_blank" rel="noopener">${esc(p.licenseName)} ↗</a></p><small>僅下載縮圖供顯示，未修改實車內容。</small></div>`;
}
function photoRetryButton(t) {
  return verifiedPhoto(t) ? `<button class="text-btn train-photo-retry" data-train-photo-retry="${esc(t.id)}" hidden aria-label="重新載入${esc(displayTrain(t).name)}的照片">照片未載入，重新載入 ↻</button>` : "";
}
function levelButtons() {
  return Object.entries(LEVELS)
    .map(
      ([id, l], i) =>
        `<button class="level-card ${progress.level === id ? "selected" : ""}" data-level="${id}" aria-pressed="${progress.level === id}"><span class="level-symbol">${["🌱", "🌿", "🌳"][i]}</span><span><strong>${l.name}</strong><small>${l.age}・${l.label}</small></span><span class="level-check" aria-hidden="true">${progress.level === id ? "✓" : "○"}</span></button>`,
    )
    .join("");
}
function card(t) {
  t = displayTrain(t);
  return `<article class="train-card ${selected === t.id ? "chosen" : ""}"><button class="train-picture" data-select="${t.id}" aria-label="選擇${esc(t.cardLabel)}" aria-pressed="${selected === t.id}">${image(t)}${tag(t)}${selected === t.id ? '<span class="chosen-label">✓ 本次列車</span>' : ""}</button><div class="train-card-body"><div><h3>${esc(t.name)}</h3><p>${esc(t.model)}</p></div><button class="info-btn" data-detail="${t.id}" aria-label="認識${esc(t.cardLabel)}">↗</button></div><small class="art-note">${artNote(t)}</small>${photoRetryButton(t)}</article>`;
}
function filterBar() {
  return `<div class="filter-controls"><div class="filter-tabs" role="group" aria-label="列車分類"><button data-filter="all" class="${filter === "all" ? "active" : ""}">全部列車</button>${Object.entries(
    labels,
  )
    .map(
      ([id, label]) =>
        `<button data-filter="${id}" class="${filter === id ? "active" : ""}">${label}</button>`,
    )
    .join(
      "",
    )}</div><label class="search-field"><span aria-hidden="true">⌕</span><span class="sr-only">搜尋列車名稱或型號</span><input id="train-search" value="${esc(search)}" placeholder="找名字或型號" type="search"></label></div>`;
}
function filteredTrains() {
  const q = search.trim().toLowerCase();
  return trains.filter(
    (t) =>
      (filter === "all" || t.category === filter) &&
      (!q ||
        [t.name, t.model, t.operator, t.cardLabel, t.displayName, t.displayModel]
          .join(" ")
          .toLowerCase()
          .includes(q)),
  );
}
function renderCards() {
  const list = filteredTrains();
  $("#train-grid").innerHTML = list.length
    ? list.map(card).join("")
    : '<p class="empty-message">這裡還沒有找到。試試「高鐵」、「磁浮」或「EMU」。</p>';
  $("#result-count").textContent = `${list.length} 款列車與名稱`;
}
function renderHome() {
  stopStory();
  main.innerHTML = homeMarkup({
    trains: trains.map(displayTrain),
    selected,
    progress,
    esc,
    image,
    resume: pausedTrip ? { train: displayTrain(pausedTrip.train), level: pausedTrip.meta.level, index: pausedTrip.index, total: pausedTrip.questions.length } : null,
  });
  storyHandle = mountStory($("#story-scene"), {
    state: storySession,
    reduced: progress.reduceMotion || motionPreference.matches,
    onRead: (text) => speak(text, true),
    onSound: chime,
    onGame: (id) => chooseMission(id, "mission"),
    onAnnounce: announce,
  });
}
function renderPlayroom() {
  stopStory();
  const journeysWereOpen = $("#theme-journeys")?.open;
  main.innerHTML = playroomMarkup({ progress, esc, category: playroomCategory,
    trains: trains.map(displayTrain), selected, image,
    resume: pausedTrip ? { train: displayTrain(pausedTrip.train), level: pausedTrip.meta.level, index: pausedTrip.index, total: pausedTrip.questions.length } : null,
    routeMarkup: journeyMarkup({ level: progress.level, completed: progress.journeysCompleted, availableGames: allowedGames(progress.level), esc }) });
  if (journeysWereOpen) $("#theme-journeys")?.setAttribute("open", "");
}
function changeGameCategory(category, focus = true) {
  if (!["math", "observe", "build", "life"].includes(category)) return;
  playroomCategory = category;
  const top = window.scrollY;
  renderPlayroom();
  window.scrollTo({ top, behavior: "instant" });
  if (focus) main.querySelector(`[data-game-category="${category}"]`)?.focus({ preventScroll: true });
}
function clearDeparture() {
  departureToken = null;
  main.inert = false;
  main.removeAttribute("aria-busy");
  document.body.classList.remove("departing");
}
function depart() {
  if (departureToken) return;
  if (
    !["home", "playroom"].includes(view) ||
    progress.reduceMotion ||
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ) {
    startTrip();
    return;
  }
  const token = Symbol();
  departureToken = token;
  document.body.classList.add("departing");
  main.inert = true;
  main.setAttribute("aria-busy", "true");
  announce("列車準備出發。下一站，發現數學！");
  setTimeout(() => {
    if (departureToken === token && ["home", "playroom"].includes(view)) startTrip();
  }, 420);
}
function chooseMission(id, source) {
  if (!Object.hasOwn(GAMES, id)) return;
  if (!allowedGames(progress.level).includes(id)) {
    const message = `${GAMES[id].name}適合 5–8 歲。請家長按「換難度」，選擇合適的年齡再玩。`;
    if ($("#home-notice")) $("#home-notice").textContent = message;
    if ($("#age-note")) $("#age-note").textContent = message;
    announce(message);
    speak(message);
    const suggested = document.querySelector("[data-level='medium']");
    suggested?.setAttribute("aria-describedby", "age-note");
    suggested?.focus({ preventScroll: pointerInteraction });
    return;
  }
  practice = id;
  selectedJourney = null;
  if (source === "mission") {
    depart();
    return;
  }
  renderHome();
  document.querySelector(`[data-${source}="${id}"]`)?.focus({ preventScroll: pointerInteraction });
  const message = `已選擇${GAMES[id].name}。搭 ${displayTrain(byId(selected)).cardLabel} 出發！`;
  announce(message);
  speak(message);
}
function renderCollection() {
  main.innerHTML = `<div class="content-wrap catalogue-page"><div class="page-intro"><div class="eyebrow dark">THE TRAIN ENCYCLOPEDIA</div><h1>火車圖鑑</h1><p>每一台列車，都有自己的名字。點圖片選車，點箭頭聽聽它的故事。</p><span class="catalogue-note">台灣列車・林鐵與觀光名稱・海外子彈列車・磁浮試驗列車</span></div>${filterBar()}<div class="collection-toolbar"><span id="result-count"></span><a href="#home" class="text-link">選好了，回去出發 →</a></div><div id="train-grid" class="train-grid"></div><p class="fineprint">圖鑑使用逐張核對的實車照片。內裝、歷史塗裝及尚未營運的列車另有標示；點箭頭可看車號證據、作者與授權。</p></div>`;
  renderCards();
}
function renderStamps() {
  const completed = progress.completed.map(byId).filter(Boolean).map(displayTrain);
  main.innerHTML = `<div class="content-wrap stamps-page"><div class="page-intro"><div class="eyebrow dark">MY RAILWAY PASSPORT</div><h1>我的鐵道護照</h1><p>已完成 <strong>${progress.trips}</strong> 趟旅程，留下 <strong>${completed.length}</strong> 款列車的紀念章。</p></div>${completed.length ? `<div class="stamp-grid">${completed.map((t) => `<button class="stamp-card" data-detail="${t.id}"><div class="stamp-image">${image(t)}<span aria-hidden="true">✦</span></div><strong>${esc(t.name)}</strong><small>${esc(t.model)}</small><span class="stamp-seal">旅程完成 ✓</span></button>`).join("")}</div>` : '<div class="empty-passport"><span aria-hidden="true">🎟</span><h2>你的第一枚紀念章在等你</h2><p>選一台喜歡的火車，完成一趟小旅程就能收藏。</p><a href="#home" class="primary-btn">出發旅行 →</a></div>'}${journeyStampsMarkup()}${pendingGiftMarkup()}${souvenirCollection(progress, { esc })}<p class="fineprint">護照存在這台裝置；清除瀏覽器資料會一起清除。所有列車都能自由選擇。</p></div>`;
}
function pendingGiftMarkup() {
  if (!progress.giftCredits) return "";
  const choices = progress.giftOffer.map(id => SOUVENIRS.find(item => item.id === id)).filter(Boolean);
  return `<section class="pending-gifts"><h2>還有 ${progress.giftCredits} 份旅途小禮物可以領</h2>${souvenirMarkup({ giftChoices: choices }, { esc })}</section>`;
}
function journeyStampsMarkup() {
  const travelled = JOURNEYS.filter(route => progress.journeysCompleted.includes(route.id));
  if (!travelled.length) return "";
  return `<section class="journey-stamps" aria-labelledby="journey-stamps-title"><h2 id="journey-stamps-title">我的小站旅程</h2><p>已完成 ${travelled.length}／${JOURNEYS.length} 條主題旅程，可以再出發找新任務。</p><div>${travelled.map(route => `<button class="secondary-btn" data-journey="${route.id}" aria-label="再玩${esc(route.name)}"><span aria-hidden="true">${route.icon}</span> ${esc(route.name)} ✓</button>`).join("")}</div></section>`;
}
function openGiftDetail(id) {
  const gift = SOUVENIRS.find(item => item.id === id);
  if (!gift || !progress.souvenirs.includes(id)) return;
  $("#gift-detail-content").innerHTML = giftDetailMarkup(gift, { esc });
  $("#gift-dialog").showModal();
}
function playGift(button) {
  const widget = button.closest("[data-gift-widget]");
  if (!widget) return;
  const kind = widget.dataset.playKind;
  const active = widget.classList.toggle("gift-active");
  const messages = {
    signal: active ? "綠燈亮了，小火車可以出發！" : "紅燈亮了，小火車等等再出發。",
    glow: active ? "亮起來了，旅途多了一道小小的光。" : "小小的光休息一下。",
    stamp: active ? "喀嚓！蓋上旅程紀念章了。" : "紀念章收起來，再蓋一次吧。",
    wind: "呼！小禮物跟著風動起來了。",
    bounce: "小禮物跳了一下，跟你打招呼！",
  };
  widget.classList.remove("gift-playing");
  void widget.offsetWidth;
  widget.classList.add("gift-playing");
  const message = messages[kind] || "小禮物跟你打招呼了！";
  widget.querySelector("[data-gift-feedback]").textContent = message;
  button.setAttribute("aria-pressed", String(active));
  announce(message);
  chime();
}
function prepareQuestionState(q) {
  Object.assign(trip, newAdventureState(q));
  trip.puzzle = q.game === "puzzle" ? newPuzzleState(q) : null;
  trip.explorer = ["luggage", "maze"].includes(q.game) ? newExplorerState(q) : null;
  trip.workshop = ["program", "balance"].includes(q.game) ? newWorkshopState(q) : null;
  trip.discovery = ["mosaic", "differences"].includes(q.game) ? newDiscoveryState(q) : null;
  trip.tickets = q.game === "tickets" ? newTicketsState(q) : null;
}
function route() {
  const page = resolvePage(location.hash);
  stopProgramRun(); clearPhotoTask(); cancelVoice(); clearDeparture();
  const alreadyRendered = view === page.view && ((view === "home" && $("#story-scene")) || (view === "playroom" && $("#playroom")));
  if (!alreadyRendered) {
    stopStory(); pauseTrip(); stopGameDock();
    view = page.view;
    trip = null;
    document.body.classList.remove("in-game"); delete document.body.dataset.game;
    if (view === "collection") renderCollection();
    else if (view === "stamps") renderStamps();
    else if (view === "playroom") renderPlayroom();
    else renderHome();
    applyPreferences();
  }
  document.querySelectorAll("[data-nav]").forEach(n => {
    const current = n.dataset.nav === view;
    n.classList.toggle("current", current);
    if (current) n.setAttribute("aria-current", "page"); else n.removeAttribute("aria-current");
  });
  if (page.openJourneys) $("#theme-journeys")?.setAttribute("open", "");
  if (page.anchor) $(`#${page.anchor}`)?.scrollIntoView({ behavior: "instant" });
  else window.scrollTo({ top: 0, behavior: "instant" });
}
function detail(id) {
  storyHandle?.pause();
  const raw = byId(id);
  if (!raw) return;
  const t = displayTrain(raw);
  $("#detail-content").innerHTML =
    `<form method="dialog" class="detail-top"><button class="close-btn" aria-label="關閉列車介紹">×</button></form>${image(t, "detail-image", false)}<div class="detail-body">${tag(t)}<h2 id="detail-title">${esc(t.name)}</h2><div class="model-badge">${esc(t.model)} <small>${t.modelKind === "type" ? "型號" : t.modelKind === "fleet" ? "車號系列" : "列車名稱／編組說明"}</small></div><p>${esc(learningDiscovery(t.id, { topic: "train" }).text)}</p><details class="train-more"><summary>更多列車知識</summary><p>${esc(t.intro)}</p><p class="train-fact">${esc(t.fact)}</p></details><div class="detail-actions"><button class="secondary-btn" data-speak="${t.id}">♪ 聽聽名字</button><button class="primary-btn" data-travel="${t.id}">搭這台出發 →</button></div>${photoCredits(t)}${photoRetryButton(t)}<div class="detail-source"><small>${artNote(t)}・${esc(t.operator)}<br>${esc(t.note || "列車名稱與型號是教材資料；圖片細節以實車為準。")}</small><a href="${esc(t.sources[0])}" target="_blank" rel="noopener">資料來源 ↗</a></div></div>`;
  $("#detail-dialog").showModal();
}
function settings() {
  if (activeProgramRun) { stopProgramRun(); renderQuestion(); }
  storyHandle?.pause();
  cancelVoice();
  clearDeparture();
  $("#settings-content").innerHTML =
    `<p>按孩子的理解程度選難度，隨時都能更換。</p><div class="settings-levels">${levelButtons()}</div><label class="setting-row"><span><strong>中文語音</strong><small>${"speechSynthesis" in window ? "使用這台裝置的中文語音" : "這台裝置沒有語音服務，仍可使用畫面提示"}</small></span><input type="checkbox" data-pref="voice" ${progress.voice ? "checked" : ""} ${"speechSynthesis" in window ? "" : "disabled"}></label><label class="setting-row"><span><strong>柔和音效</strong><small>完成任務時的小小慶祝</small></span><input type="checkbox" data-pref="effects" ${progress.effects ? "checked" : ""}></label><label class="setting-row"><span><strong>減少動畫</strong><small>讓畫面更加平靜</small></span><input type="checkbox" data-pref="reduceMotion" ${progress.reduceMotion ? "checked" : ""}></label><label class="setting-row"><span><strong>跨十加減挑戰</strong><small>只在 7–8 歲模式啟用</small></span><input type="checkbox" data-pref="challenge" ${progress.challenge ? "checked" : ""}></label><div class="clear-record"><button id="clear-progress" class="danger-btn">清除本機紀錄</button><p>只會清除這台裝置的護照與設定。</p><div id="clear-confirm"></div></div>`;
  $("#settings-dialog").showModal();
}
function startTrip() {
  stopProgramRun();
  clearPhotoTask();
  if (practice !== "mixed" && !allowedGames(progress.level).includes(practice)) practice = "mixed";
  stopStory();
  clearDeparture();
  cancelVoice();
  view = "game";
  const train = byId(selected);
  const seed = window.crypto?.getRandomValues
    ? crypto.getRandomValues(new Uint32Array(1))[0] : Math.floor(Math.random() * 4294967296);
  const meta = {
    level: progress.level, trainId: train.id, practice,
    challenge: progress.challenge, seed,
    recentQuestions: [...progress.recentQuestions], recentGames: [...progress.recentGames],
    journey: selectedJourney, contentVersion: "1.8.0",
  };
  pausedTrip = null;
  trip = {
    meta,
    train,
    questions: createTrip({
      level: progress.level,
      train,
      trains,
      challenge: progress.challenge,
      practice,
      recentQuestions: progress.recentQuestions,
      recentGames: progress.recentGames,
      rng: seededRandom(seed),
      journey: selectedJourney,
    }),
    index: 0,
    attempts: 0,
    solved: false,
    assisted: false,
    awarded: false,
    order: [],
    cargo: 0,
    memory: newMemoryState(),
    memoryPeek: false,
    counted: new Set(),
    boardingInput: "",
    feedback: "",
  };
  rememberTrip(progress, trip.questions);
  persist();
  prepareQuestionState(trip.questions[0]);
  renderQuestion();
  speak(spokenQuestionText(trip.questions[0]));
  main.focus({ preventScroll: pointerInteraction });
  window.scrollTo({ top: 0, behavior: "instant" });
}
function dotCard(n) {
  return n === 0
    ? '<span class="zero-dots">沒有</span>'
    : `<span class="dot-card" aria-label="${n} 個點">${Array.from({ length: n }, () => "<i></i>").join("")}</span>`;
}
const person = (i, clicked = false, extra = "") =>
  `<svg viewBox="0 0 48 60" aria-hidden="true" class="person-svg ${extra}"><circle cx="24" cy="12" r="9" fill="${["#e6b08d", "#bf886d", "#d5a383"][i % 3]}"/><path d="M15 11q0-15 18-4v6q-3-9-18-2" fill="#343d40"/><rect x="12" y="24" width="24" height="24" rx="9" fill="${clicked ? "#1c7e70" : ["#eeaa64", "#698b93", "#a6a081", "#ac817a"][i % 4]}"/><path d="M18 47v9m12-9v9" stroke="#334b54" stroke-width="7" stroke-linecap="round"/>${clicked ? '<path d="M18 35l4 4 9-10" fill="none" stroke="white" stroke-width="3"/>' : ""}</svg>`;
function ticketPile(n) {
  return `<div class="ticket-pile">${Array.from({ length: n }, () => '<span class="tiny-ticket" aria-hidden="true">🎟</span>').join("")}</div>`;
}
function gameScene(q) {
  if (q.game === "tickets") return ticketsScene(q, trip, { esc });
  if (["program", "balance"].includes(q.game)) return workshopScene(q, trip, { esc });
  if (["mosaic", "differences"].includes(q.game)) return discoveryScene(q, trip, { esc });
  if (q.game === "puzzle") return puzzleScene(q, trip, { esc });
  if (["luggage", "maze"].includes(q.game)) return explorerScene(q, trip, { esc });
  if (["tracks", "sharing", "treasure"].includes(q.game))
    return adventureScene(q, trip);
  if (["pattern", "cargo", "memory", "clock"].includes(q.game))
    return activityScene(q, trip, { byId: gameById, image: gameImage, esc });
  if (q.game === "count")
    return countingScene(q, trip, { person });
  if (q.game === "identify")
    return '<div class="identify-intro"><span aria-hidden="true">🚆</span><p>仔細看看列車卡，<br>找到它的名字。</p></div>';
  if (q.game === "compare")
    return `<div class="compare-stage"><div><span class="stage-label">左邊的車票</span>${ticketPile(q.left)}</div><div><span class="stage-label">右邊的車票</span>${ticketPile(q.right)}</div></div>`;
  if (q.game === "boarding") {
    return arithmeticScene(q, { solved: trip.solved, input: trip.boardingInput, touch: touchDevice() && !trip.nativeKeyboard });
  }
  if (q.game === "order")
    return `<div class="sorting-stage"><span class="stage-label">數學示意列車 · 點一下就能排車廂</span><div class="sorting-track"><span class="toy-engine" aria-label="示意列車車頭">🚂</span>${q.answer.map((_, i) => `<button class="carriage-slot ${trip.order[i] !== undefined ? "filled" : ""}" data-remove-order="${i}" ${trip.solved ? "disabled" : ""} aria-label="第 ${i + 1} 節${trip.order[i] !== undefined ? `，數字 ${trip.order[i]}，點選移除` : "，空車廂"}">${trip.order[i] ?? "?"}</button>`).join("")}</div><div class="sorting-bank">${q.numbers.map((n) => `<button class="number-carriage" data-order="${n}" ${trip.order.includes(n) || trip.solved ? "disabled" : ""} aria-label="放入數字 ${n}">${n}</button>`).join("")}</div><div class="sort-actions"><button class="text-btn" id="order-reset" ${trip.solved ? "disabled" : ""}>重新排一次</button><button class="primary-btn" id="order-submit" ${trip.order.length !== q.answer.length || trip.solved ? "disabled" : ""}>排好了 ✓</button></div></div>`;
  return "";
}
function answerMarkup(q) {
  if (
    ["tickets", "program", "balance", "mosaic", "differences", "puzzle", "luggage", "maze", "boarding", "order", "cargo", "memory", "tracks", "sharing", "treasure"].includes(
      q.game,
    )
  )
    return "";
  return `<div class="answers ${q.game === "identify" ? "picture-answers" : ""}">${q.choices
    .map((value) => {
      const disabled = trip.solved;
      if (q.game === "identify") {
        const t = gameById(value);
        return `<button class="answer-card" data-answer="${value}" ${disabled ? "disabled" : ""}>${gameImage(t)}<strong>${esc(t.name)}</strong><small>${esc(t.model)}</small></button>`;
      }
      if (q.game === "pattern")
        return `<button class="answer-number pattern-answer" data-answer="${esc(value)}" ${disabled ? "disabled" : ""} aria-label="${patternName(q, value)}">${patternToken(q, value)}<small>${patternName(q, value)}</small></button>`;
      const label =
        q.game === "clock"
          ? clockLabel(value)
          : q.game === "compare"
            ? { left: "左邊", right: "右邊", equal: "一樣多" }[value]
            : q.level === "small"
              ? dotCard(value)
              : value;
      return `<button class="answer-number ${q.game === "clock" ? "clock-answer" : ""}" data-answer="${esc(value)}" ${disabled ? "disabled" : ""} aria-label="${["compare", "clock"].includes(q.game) ? label : `答案 ${value}`}">${label}</button>`;
    })
    .join("")}</div>`;
}
function questionHeading(q) {
  const guide = learningGuide(q, trip);
  return '<div class="question-head"><span class="question-icon" aria-hidden="true">' + gameIcons[q.game] + '</span><h1 id="question-title">' + esc(guide.title) + '</h1></div>' +
    (!trip.solved ? '<p class="learning-action" id="learning-action"><small>這一步</small><span>' + esc(guide.action) + '</span></p>' : '');
}
function completedDiscovery(q) {
  if (!trip.solved) return '';
  const id = ['identify', 'puzzle'].includes(q.game) ? q.target : trip.train.id;
  return discoveryMarkup(learningDiscovery(id, { index: trip.index }), { esc });
}
function spokenQuestionText(q) {
  if (!q) return '';
  const guide = learningGuide(q, trip);
  const action = main.querySelector('.learning-action > span')?.textContent || guide.action;
  return q.prompt + ' ' + action + ' ' + guide.help +
    (q.game === 'program' ? ' ' + (main.querySelector('.program-status')?.textContent || '') : '');
}
function renderQuestion() {
  const focusedControl = !pointerInteraction && main.contains(document.activeElement) ? document.activeElement.id : null;
  if (!trip || trip.awarded) return;
  const q = trip.questions[trip.index];
  const paths = gamePhotoPaths(q), photoStatus = photoLoader.status(paths);
  activePhotoTask = { paths, status: photoStatus, key: `${trip.meta.seed}:${trip.index}:${q.game}` };
  const route = journeyById(trip.meta.journey);
  const scrollKey = `${trip.meta.seed}:${trip.meta.trainId}:${trip.index}:${q.game}`;
  const selectors = [".mosaic-paint-board", ".program-queue", ".cargo-boxes", ".balance-load", "#ticket-payment-0", "#ticket-payment-1"];
  if (questionScroll.key !== scrollKey) questionScroll = { key: scrollKey, positions: {} };
  else for (const selector of selectors) {
    const element = main.querySelector(selector);
    if (element) questionScroll.positions[selector] = { top: element.scrollTop, left: element.scrollLeft };
  }
  document.body.classList.add("in-game");
  document.body.dataset.game = q.game;
  main.innerHTML = `<div class="game-wrap"><div class="game-top"><button id="trip-exit" class="text-btn" aria-label="暫停旅程，回遊戲室">← 遊戲室</button><span class="game-name">${gameLabels[q.game]}</span><div class="game-tools"><button id="question-replay" class="icon-btn" aria-label="聽題目">🔊</button>${fullscreenButton()}</div></div><div class="trip-progress" aria-label="第 ${trip.index + 1} 站，共 ${trip.questions.length} 站">${trip.questions.map((station, i) => `<span class="progress-stop ${i < trip.index ? "done" : ""} ${i === trip.index ? "current" : ""}"><i>${i < trip.index ? "✓" : i + 1}</i><small>${esc(route?.stationLabels[q.level][i] || stationNames[station.game])}</small></span>`).join("")}</div><section class="game-panel">${questionHeading(q)}<div class="game-stage" id="game-stage">${gameScene(q)}</div>${answerMarkup(q)}${completedDiscovery(q)}<div class="feedback ${trip.solved ? "success" : ""}" role="status" aria-live="polite">${esc(trip.feedback || "")}</div><div class="question-actions" id="game-actions"><button id="hint-show" class="text-btn" ${trip.solved ? "disabled" : ""}>☀ 一起想一想</button>${trip.solved ? `<button id="question-next" class="primary-btn">${trip.index === trip.questions.length - 1 ? "抵達終點，收集紀念章" : "前往下一站"} →</button>` : ""}</div></section><div class="trip-train-note">${image(trip.train)}<span><strong>${esc(displayTrain(trip.train).name)}</strong><small>${esc(displayTrain(trip.train).model)} · 今天一起旅行的列車</small></span><button data-speak="${trip.train.id}" class="icon-btn" aria-label="聽今天的列車名字">♪</button></div></div>`;
  arrangeGameActions(q);
  watchGameDock();
  preparePhotoDisplay(photoStatus);
  for (const [selector, position] of Object.entries(questionScroll.positions)) {
    const element = main.querySelector(selector);
    if (element) element.scrollTo({ top: position.top, left: position.left, behavior: "instant" });
  }
  updateFullscreenControl();
  syncKeyboardDock();
  saveCurrentTrip();
  if (focusedControl) {
    const control = document.getElementById(focusedControl);
    if (control && !control.disabled && main.contains(control)) control.focus({ preventScroll: true });
  }
}
function gamePhotoPaths(q) {
  if (q.game === "puzzle") return [q.image];
  const ids = q.game === "memory" ? q.pairs : q.game === "identify" ? q.choices : [];
  return ids.map(id => trainImage(byId(id), trip.meta.contentVersion));
}
function preparePhotoDisplay(status) {
  for (const picture of main.querySelectorAll("img[src]")) {
    if (!/^assets\/images\//.test(picture.getAttribute("src"))) continue;
    const original = picture.getAttribute("src").split("?")[0], source = photoLoader.source(original);
    if (source !== picture.getAttribute("src")) picture.setAttribute("src", source);
  }
  if (status === "ready") return;
  $("#game-stage").hidden = true;
  const choices = main.querySelector(".picture-answers");
  if (choices) choices.hidden = true;
  $("#game-stage").insertAdjacentHTML("beforebegin", `<div class="photo-load-state" role="status"><span aria-hidden="true">▧</span><p>${status === "error" ? "照片還沒載入，請再試一次。剛剛放好的位置會保留。" : "照片準備中，等一下就能玩囉。"}</p>${status === "error" ? '<button id="photo-retry" class="primary-btn">重新載入照片 ↻</button>' : ""}</div>`);
  for (const button of main.querySelectorAll("[data-answer], [data-memory], [data-puzzle-piece], [data-puzzle-slot], #puzzle-submit, #puzzle-preview, #puzzle-reset, #memory-hide")) button.disabled = true;
}
function arrangeGameActions(q) {
  const dock = $("#game-actions");
  const feedback = main.querySelector(".feedback");
  if (feedback) dock.prepend(feedback);
  const primary = {
    boarding: "boarding-submit", puzzle: "puzzle-submit", luggage: "luggage-submit",
    tracks: "tracks-submit", sharing: "sharing-submit", order: "order-submit", cargo: "cargo-submit",
    memory: "memory-hide",
    program: "program-run", balance: "balance-check", mosaic: "mosaic-submit", tickets: "tickets-check",
  }[q.game];
  const button = primary ? $(`#${primary}`) : null;
  if (button && !trip.solved) {
    if (q.game === "boarding") button.setAttribute("form", "boarding-form");
    dock.append(button);
    if (q.game === "memory") {
      button.classList.remove("secondary-btn");
      button.classList.add("primary-btn");
    }
  }
  if (q.game === "cargo") {
    for (const item of main.querySelectorAll("[data-load]")) {
      item.setAttribute("aria-label", `放入 ${item.dataset.load} 箱貨物`);
      item.textContent = `＋ ${item.dataset.load} 箱`;
    }
  }
  if (q.game === "sharing" && !trip.solved) {
    const reset = $("#sharing-reset");
    reset.textContent = "重分";
    reset.setAttribute("aria-label", "全部放回籃子，重新分");
    dock.insertBefore(reset, button);
    button.textContent = "分好了 ✓";
    button.setAttribute("aria-label", "大家一樣多了，送出結果");
  }
  if (["program", "mosaic", "tickets"].includes(q.game) && !trip.solved) {
    const reset = $(`#${q.game}-reset`);
    reset.textContent = q.game === "program" ? "重排" : q.game === "tickets" ? "取回" : "清空";
    reset.setAttribute("aria-label", q.game === "program" ? "清空指令，重新排" : q.game === "tickets" ? "取回所有代幣，重新分配" : "清空畫板，重新拼搭");
    dock.insertBefore(reset, button);
    button.textContent = q.game === "program" ? "出發 →" : q.game === "tickets" ? "付好了 ✓" : "拼好了 ✓";
    if (q.game === "program" && trip.programRunning) {
      button.disabled = false;
      button.textContent = "停車 ▪";
      button.setAttribute("aria-label", "停車，保留指令和目前位置");
    }
  }
  if (q.game === "puzzle" && !trip.solved) {
    const preview = $("#puzzle-preview");
    preview.setAttribute("aria-label", trip.puzzle.preview ? "收起原圖" : "看看原圖");
    preview.textContent = "🖼";
    preview.classList.add("dock-preview");
    dock.prepend(preview);
    button.textContent = "拼好了 ✓";
    button.setAttribute("aria-label", "拼好了，送出拼圖");
  }
  if (!trip.solved && !primary && q.game !== "identify") {
    const choices = main.querySelector(".answers");
    if (choices) dock.append(choices);
  }
  if (!trip.solved && button && !button.disabled) {
    const action = {
      order: "排好了，按「排好了」檢查。",
      puzzle: "放滿了，按「拼好了」檢查。",
      luggage: "放好了，按「分好了」檢查。",
      sharing: "分完了，按「分好了」檢查。",
    }[q.game];
    if (action) main.querySelector(".learning-action > span").textContent = action;
  }
}
function answer(value) {
  if (!trip || trip.solved) return;
  const q = trip.questions[trip.index];
  if (isCorrect(q, value)) {
    trip.solved = true;
    trip.feedback = "完成了！" + learningGuide(q, trip).success;
    chime();
    speak(trip.feedback);
    renderQuestion();
    $("#question-next")?.focus({ preventScroll: pointerInteraction });
    revealFeedback();
  } else {
    trip.attempts++;
    trip.feedback = "還沒答對，再想一次。需要幫忙時，可以點「一起想一想」。";
    speak(trip.feedback);
    renderQuestion();
    revealFeedback();
  }
}
function hint() {
  if (!trip || trip.solved) return;
  const q = trip.questions[trip.index];
  trip.assisted = true;
  trip.feedback = learningGuide(q, trip).help;
  renderQuestion();
  speak(trip.feedback);
  revealFeedback();
}
function submitArithmetic() {
  const q = trip?.questions[trip.index];
  if (q?.game !== "boarding" || trip.solved) return;
  trip.boardingInput = $("#boarding-input").value;
  const value = parseArithmeticAnswer(trip.boardingInput, LEVELS[q.level].max);
  if (value === null) {
    trip.feedback = `請輸入 0 到 ${LEVELS[q.level].max} 的整數。`;
    $(".feedback").textContent = trip.feedback;
    $("#boarding-input").focus({ preventScroll: pointerInteraction });
    return;
  }
  answer(value);
  if (!trip.solved) $("#boarding-input")?.focus({ preventScroll: pointerInteraction });
}
function next() {
  if (!trip?.solved || trip.awarded) return;
  if (trip.index < trip.questions.length - 1) {
    trip.index++;
    Object.assign(trip, {
      attempts: 0,
      solved: false,
      assisted: false,
      order: [],
      cargo: 0,
      memory: newMemoryState(),
      memoryPeek: false,
      counted: new Set(),
      boardingInput: "",
      feedback: "",
    });
    prepareQuestionState(trip.questions[trip.index]);
    renderQuestion();
    window.scrollTo({ top: 0, behavior: "instant" });
    speak(spokenQuestionText(trip.questions[trip.index]));
    $("#question-title").setAttribute("tabindex", "-1");
    $("#question-title").focus({ preventScroll: pointerInteraction });
  } else finishTrip();
}
function stopProgramRun() {
  programPlayer.stop();
  if (activeProgramRun) {
    activeProgramRun.trip.programRunning = false;
    activeProgramRun.trip.feedback = "火車停在這裡，指令和位置都保留了；按出發會從起點重新走。";
  }
  activeProgramRun = null;
}
function showProgramCommand(index) {
  const queue = main.querySelector(".program-queue"), command = main.querySelector(`[data-program-remove="${index}"]`);
  if (!queue || !command) return;
  const commandBox = command.getBoundingClientRect(), queueBox = queue.getBoundingClientRect();
  queue.scrollLeft += commandBox.left - queueBox.left - (queue.clientWidth - commandBox.width) / 2;
}
function startProgramRun() {
  const q = trip?.questions[trip.index];
  if (q?.game !== "program" || trip.solved || trip.programRunning || !trip.workshop.commands.length) return;
  stopProgramRun();
  const run = { trip, index: trip.index }, result = evaluateProgram(q, trip.workshop.commands);
  activeProgramRun = run;
  trip.programRunning = true;
  trip.workshop.programChecked = false;
  trip.feedback = "火車正在照你排的方向走，看看每一步。";
  const current = () => activeProgramRun === run && trip === run.trip && trip.index === run.index && view === "game" && !trip.awarded;
  programPlayer.start(result, {
    onStep(step) {
      if (!current()) return;
      Object.assign(trip.workshop, { programPosition: step.position, programTrace: [...step.trace] });
      renderQuestion();
      showProgramCommand(Math.max(0, step.index - 1));
    },
    onDone() {
      if (!current()) return;
      activeProgramRun = null;
      trip.programRunning = false;
      Object.assign(trip.workshop, { programChecked: true, programPosition: result.position, programTrace: [...result.trace] });
      if (result.arrived) answer("arrived");
      else {
        trip.attempts++;
        trip.feedback = result.blocked ? "這一步碰到牆了。點指令修改，再按出發試一次。" : "這段走完了，還沒到站。可以再接幾個方向，按出發試一次。";
        renderQuestion();
        showProgramCommand(result.blocked ? result.trace.length - 1 : trip.workshop.commands.length - 1);
        speak(trip.feedback);
        $("#program-run")?.focus({ preventScroll: pointerInteraction });
      }
    },
  });
}
function stepMaze(direction) {
  const q = trip?.questions[trip.index];
  if (q?.game !== "maze" || trip.solved) return;
  const before = trip.explorer;
  trip.explorer = moveMaze(q, before, direction);
  if (before === trip.explorer) {
    trip.feedback = "這邊有牆，換個方向試試看。";
    $(".feedback").textContent = trip.feedback;
    announce(trip.feedback);
    updateDockSpace();
    return;
  }
  trip.feedback = "";
  if (trip.explorer.mazePosition === q.finish) answer("arrived");
  else {
    renderQuestion();
    document.querySelector(`[data-maze-direction="${direction}"]`)?.focus({ preventScroll: pointerInteraction });
    announce(`小火車在第 ${Math.floor(trip.explorer.mazePosition / q.columns) + 1} 排，第 ${trip.explorer.mazePosition % q.columns + 1} 格。`);
  }
}
function finishTrip() {
  if (!trip) return;
  stopProgramRun();
  clearPhotoTask();
  view = "finish";
  stopGameDock();
  clearTripSession(tripStorage);
  pausedTrip = null;
  document.body.classList.remove("in-game");
  delete document.body.dataset.game;
  if (!trip.awarded) {
    trip.awarded = true;
    progress.trips++;
    enqueueGift(progress);
    if (!progress.completed.includes(trip.train.id))
      progress.completed.push(trip.train.id);
    if (trip.meta.journey && !progress.journeysCompleted.includes(trip.meta.journey)) progress.journeysCompleted.push(trip.meta.journey);
    persist();
  }
  const t = displayTrain(trip.train);
  const route = journeyById(trip.meta.journey);
  trip.giftChoices = progress.giftOffer.map(id => SOUVENIRS.find(item => item.id === id)).filter(Boolean);
  main.innerHTML = `<div class="finish-wrap"><div class="eyebrow dark">JOURNEY COMPLETED</div><h1>${route ? esc(route.name + "，任務完成！") : "抵達終點，做得好！"}</h1><p>${route ? esc(route.arrivalText) : "每一次發現，都值得一枚紀念章。"}</p><div class="finish-stamp">${image(t, "", false)}<span class="finish-stars" aria-hidden="true">✦</span><h2>${esc(t.name)}</h2><p>${esc(t.model)}</p><div class="stamp-seal">我的鐵道旅程 · 完成 ✓</div></div><p class="finish-note">今天認識了${esc(t.name)}。下次再一起出發吧！</p><div id="trip-gift">${souvenirMarkup(trip, { esc })}</div><div class="finish-actions"><button id="trip-new" class="primary-btn">換台列車，玩新任務 →</button><button id="trip-again" class="secondary-btn">同台列車，再練新題</button><a href="#stamps" class="secondary-btn">看看我的集章</a><a href="#home" class="text-btn">休息一下</a></div></div>`;
  speak(`抵達終點，做得好！今天一起搭乘了${t.name}。`);
  main.focus({ preventScroll: pointerInteraction });
}
document.addEventListener("click", (event) => {
  const nav = event.target.closest('a[href^="#"]');
  if (nav?.getAttribute("href") === "#main") {
    event.preventDefault();
    main.focus({ preventScroll: pointerInteraction });
    main.scrollIntoView({ behavior: "instant" });
    return;
  }
  if (
    nav &&
    ["#home", "#playroom", "#collection", "#stamps"].includes(nav.getAttribute("href")) &&
    location.hash === nav.getAttribute("href")
  ) {
    event.preventDefault();
    route();
    window.scrollTo({ top: 0, behavior: "instant" });
    return;
  }
  const b = event.target.closest("button");
  if (!b) return;
  if (b.dataset.gameCategory && view === "playroom") { changeGameCategory(b.dataset.gameCategory); return; }
  if (b.dataset.trainPhotoRetry) {
    const train = byId(b.dataset.trainPhotoRetry);
    if (!train) return;
    const path = trainImage(train);
    if (path) photoLoader.retry([path]);
    if (view === "collection") renderCards();
    if ($("#detail-dialog").open) detail(train.id);
    return;
  }
  if (b.dataset.journey) {
    const route = journeyById(b.dataset.journey);
    if (!route) return;
    selectedJourney = route.id;
    practice = "mixed";
    depart();
    announce(route.departureText);
    return;
  }
  if (b.dataset.inspectGift) {
    openGiftDetail(b.dataset.inspectGift);
    return;
  }
  if (b.dataset.playGift) {
    playGift(b);
    return;
  }
  if (b.dataset.giftChoice) {
    const gift = claimGift(progress, b.dataset.giftChoice);
    if (!gift) return;
    persist();
    if (trip?.awarded && !trip.gift && $("#trip-gift")) {
      trip.gift = gift;
      $("#trip-gift").innerHTML = souvenirMarkup(trip, { esc });
      $("#trip-gift [data-play-gift]")?.focus({ preventScroll: pointerInteraction });
    } else {
      renderStamps();
      openGiftDetail(gift.id);
    }
    chime();
    announce(`已收藏${gift.name}，還有 ${progress.giftCredits} 份小禮物可以領。`);
    speak(`${gift.name}。${gift.story}`);
    return;
  }
  if (b.dataset.level) {
    progress.level = b.dataset.level;
    if (
      practice !== "mixed" &&
      !allowedGames(progress.level).includes(practice)
    )
      practice = "mixed";
    persist();
    if ($("#settings-dialog").open) {
      $("#settings-dialog").close();
      settings();
    }
    if (["home", "playroom"].includes(view)) {
      if (view === "home") renderHome(); else renderPlayroom();
      if (!$("#settings-dialog").open)
        document.querySelector(`[data-level="${progress.level}"]`)?.focus({ preventScroll: pointerInteraction });
    }
    return;
  }
  if (b.dataset.filter) {
    filter = b.dataset.filter;
    document
      .querySelectorAll("[data-filter]")
      .forEach((x) =>
        x.classList.toggle("active", x.dataset.filter === filter),
      );
    renderCards();
    return;
  }
  if (b.dataset.select) {
    selected = b.dataset.select;
    if (view === "home") renderHome();
    else if (view === "playroom") renderPlayroom();
    else renderCards();
    const t = displayTrain(byId(selected));
    if ($("#selected-name")) $("#selected-name").textContent = t.cardLabel;
    speak(t.intro);
    announce(`已選擇${t.cardLabel}`);
    document.querySelector(`[data-select="${selected}"]`)?.focus({ preventScroll: pointerInteraction });
    return;
  }
  if (b.dataset.detail) {
    detail(b.dataset.detail);
    return;
  }
  if (b.dataset.speak) {
    speak(learningDiscovery(b.dataset.speak, { topic: "train" }).text, true);
    return;
  }
  if (b.dataset.travel) {
    selected = b.dataset.travel;
    $("#detail-dialog").close();
    practice = "mixed";
    selectedJourney = null;
    startTrip();
    return;
  }
  if (b.dataset.answer !== undefined) {
    const q = trip?.questions[trip.index];
    answer(
      q && ["count", "boarding", "clock"].includes(q.game)
        ? Number(b.dataset.answer)
        : b.dataset.answer,
    );
    return;
  }
  if (b.dataset.digit !== undefined && trip && !trip.solved && trip.questions[trip.index].game === "boarding") {
    const input = $("#boarding-input");
    const digit = b.dataset.digit;
    const current = /^\d{0,2}$/.test(input.value) ? input.value : "";
    input.value = digit === "clear" ? "" : digit === "backspace" ? current.slice(0, -1) : (current === "0" ? digit : current + digit).slice(0, 2);
    trip.boardingInput = input.value;
    announce(input.value ? `已輸入 ${input.value}。` : "答案已清空。");
    return;
  }
  if (b.dataset.count !== undefined && trip && !trip.solved) {
    const i = Number(b.dataset.count);
    if (!trip.counted.has(i)) {
      trip.counted.add(i);
      announce("這位乘客已作記號，請你自己數。" );
      $("#game-stage").innerHTML = gameScene(trip.questions[trip.index]);
      saveCurrentTrip();
    }
    return;
  }
  if (b.dataset.order !== undefined && trip && !trip.solved) {
    const n = Number(b.dataset.order);
    if (!trip.order.includes(n)) trip.order.push(n);
    trip.feedback = "";
    renderQuestion();
    (document.querySelector("[data-order]:not(:disabled)") || $("#order-submit"))?.focus({ preventScroll: pointerInteraction });
    return;
  }
  if (b.dataset.removeOrder !== undefined && trip && !trip.solved) {
    const index = Number(b.dataset.removeOrder);
    if (trip.order[index] === undefined) {
      trip.feedback = "先點下面的數字車廂，它會排進空位。";
      $(".feedback").textContent = trip.feedback;
      announce(trip.feedback); updateDockSpace(); return;
    }
    trip.order.splice(index, 1);
    renderQuestion();
    return;
  }
  if (b.dataset.mood) {
    mood = b.dataset.mood;
    renderHome();
    document.querySelector(`[data-mood="${mood}"]`)?.focus({ preventScroll: pointerInteraction });
    announce(mood === "blue" ? "換成暮色氣氛。" : "換成暖陽氣氛。");
    return;
  }
  if (b.dataset.destination || b.dataset.mission) {
    chooseMission(
      b.dataset.destination || b.dataset.mission,
      b.dataset.destination ? "destination" : "mission",
    );
    return;
  }
  if (b.dataset.quickGame) {
    chooseMission(b.dataset.quickGame, "mission");
    return;
  }
  const q = trip?.questions[trip.index];
  if (trip?.programRunning && (b.dataset.programDirection || b.dataset.programRemove !== undefined || b.id === "program-reset")) return;
  if (q && !trip.awarded && view === "game" && ["identify", "memory", "puzzle"].includes(q.game)
    && photoLoader.status(gamePhotoPaths(q)) !== "ready"
    && !["photo-retry", "trip-exit", "hint-show", "question-replay", "question-next", "game-fullscreen"].includes(b.id)) return;
  if (b.dataset.ticketSelect !== undefined && q?.game === "tickets" && !trip.solved) {
    trip.tickets = selectTicket(q, trip.tickets, Number(b.dataset.ticketSelect));
    trip.feedback = "";
    renderQuestion();
    document.querySelector(`[data-ticket-select="${trip.tickets.activeTicket}"]`)?.focus({ preventScroll: pointerInteraction });
    return;
  }
  if ((b.dataset.ticketPay !== undefined || b.dataset.ticketRemove !== undefined) && q?.game === "tickets" && !trip.solved) {
    const paying = b.dataset.ticketPay !== undefined;
    trip.tickets = (paying ? payToken : returnToken)(q, trip.tickets, Number(paying ? b.dataset.ticketPay : b.dataset.ticketRemove));
    trip.feedback = "";
    renderQuestion();
    document.querySelector(paying ? "[data-ticket-pay]:not(:disabled)" : `[data-ticket-pay="${b.dataset.ticketRemove}"]`)?.focus({ preventScroll: pointerInteraction });
    return;
  }
  if (b.dataset.programDirection && q?.game === "program" && !trip.solved) {
    trip.workshop = appendCommand(q, trip.workshop, b.dataset.programDirection);
    trip.feedback = "";
    renderQuestion();
    const queue = main.querySelector(".program-queue");
    queue.scrollLeft = queue.scrollWidth;
    document.querySelector(`[data-program-direction="${b.dataset.programDirection}"]`)?.focus({ preventScroll: pointerInteraction });
    return;
  }
  if (b.dataset.programRemove !== undefined && q?.game === "program" && !trip.solved) {
    trip.workshop = removeCommand(q, trip.workshop, Number(b.dataset.programRemove));
    trip.feedback = "";
    renderQuestion();
    document.querySelector("[data-program-direction]")?.focus({ preventScroll: pointerInteraction });
    return;
  }
  if (b.dataset.balanceWeight !== undefined && q?.game === "balance" && !trip.solved) {
    trip.workshop = addWeight(q, trip.workshop, Number(b.dataset.balanceWeight));
    trip.feedback = "";
    renderQuestion();
    document.querySelector(`[data-balance-weight="${b.dataset.balanceWeight}"]`)?.focus({ preventScroll: pointerInteraction });
    return;
  }
  if (b.dataset.balanceRemove !== undefined && q?.game === "balance" && !trip.solved) {
    trip.workshop = removeWeight(q, trip.workshop, Number(b.dataset.balanceRemove));
    trip.feedback = "";
    renderQuestion();
    document.querySelector("[data-balance-weight]")?.focus({ preventScroll: pointerInteraction });
    return;
  }
  if (b.dataset.mosaicColor && q?.game === "mosaic" && !trip.solved) {
    trip.discovery = selectMosaicColor(q, trip.discovery, b.dataset.mosaicColor);
    renderQuestion();
    document.querySelector(`[data-mosaic-color="${b.dataset.mosaicColor}"]`)?.focus({ preventScroll: pointerInteraction });
    return;
  }
  if (b.dataset.mosaicCell !== undefined && q?.game === "mosaic" && !trip.solved) {
    const index = Number(b.dataset.mosaicCell);
    trip.discovery = paintMosaicCell(q, trip.discovery, index);
    trip.feedback = "";
    renderQuestion();
    document.querySelector(`[data-mosaic-cell="${index}"]`)?.focus({ preventScroll: pointerInteraction });
    return;
  }
  if (b.dataset.differenceCell !== undefined && q?.game === "differences" && !trip.solved) {
    const previous = trip.discovery;
    trip.discovery = findDifference(q, previous, Number(b.dataset.differenceCell));
    if (previous === trip.discovery) {
      trip.feedback = "這一區看起來一樣，再比一比其他地方。";
      $(".feedback").textContent = trip.feedback;
    } else if (trip.discovery.differencesFound.size === q.answer) answer(q.answer);
    else {
      trip.feedback = "找到一處了！再看看其他地方。";
      renderQuestion();
      document.querySelector("[data-difference-cell]:not(:disabled)")?.focus({ preventScroll: pointerInteraction });
    }
    return;
  }
  if (b.dataset.puzzlePiece !== undefined && q?.game === "puzzle" && !trip.solved) {
    trip.puzzle = selectPuzzlePiece(q, trip.puzzle, Number(b.dataset.puzzlePiece));
    trip.feedback = "";
    renderQuestion();
    document.querySelector("[data-puzzle-slot]")?.focus({ preventScroll: pointerInteraction });
    announce("選好了拼圖片，再點想放的位置。");
    return;
  }
  if (b.dataset.puzzleSlot !== undefined && q?.game === "puzzle" && !trip.solved) {
    const slot = Number(b.dataset.puzzleSlot);
    if (trip.puzzle.selectedPiece === null && trip.puzzle.placements[slot] === null) {
      trip.feedback = "先點下方一片拼圖，再點空格放進去。";
      $(".feedback").textContent = trip.feedback;
      announce(trip.feedback); updateDockSpace(); return;
    }
    trip.puzzle = placePuzzlePiece(q, trip.puzzle, slot);
    renderQuestion();
    document.querySelector(`[data-puzzle-slot="${slot}"]`)?.focus({ preventScroll: pointerInteraction });
    announce("拼圖片的位置更新了，可以繼續拼或取回。");
    return;
  }
  if (b.dataset.luggageItem !== undefined && q?.game === "luggage" && !trip.solved) {
    const itemIndex = Number(b.dataset.luggageItem);
    trip.explorer = selectLuggage(q, trip.explorer, itemIndex);
    trip.feedback = "";
    renderQuestion();
    if (trip.explorer.luggageSelected === null) {
      document.querySelector(`[data-luggage-item="${itemIndex}"]`)?.focus({ preventScroll: pointerInteraction });
      announce("行李放回月台了。");
    } else {
      document.querySelector("[data-luggage-bin]")?.focus({ preventScroll: pointerInteraction });
      announce("選好了行李，再點要放的籃子。");
    }
    return;
  }
  if (b.dataset.luggageBin !== undefined && q?.game === "luggage" && !trip.solved) {
    const bin = b.dataset.luggageBin;
    trip.explorer = putLuggage(q, trip.explorer, bin);
    trip.feedback = "";
    renderQuestion();
    (document.querySelector(".luggage-rack [data-luggage-item]") || $("#luggage-submit"))?.focus({ preventScroll: pointerInteraction });
    announce("行李放好了；想換籃子，可以再點那件行李。");
    return;
  }
  if (b.dataset.mazeDirection && q?.game === "maze" && !trip.solved) {
    stepMaze(b.dataset.mazeDirection);
    return;
  }
  if (b.dataset.rotate !== undefined && q?.game === "tracks" && !trip.solved) {
    const index = Number(b.dataset.rotate);
    if (q.tiles[index]?.kind !== "empty")
      trip.rotations[index] = (trip.rotations[index] + 1) % 4;
    trip.feedback = "";
    renderQuestion();
    document.querySelector(`[data-rotate="${index}"]`)?.focus({ preventScroll: pointerInteraction });
    announce(`第 ${index + 1} 格軌道轉好了。`);
    return;
  }
  if (
    (b.dataset.share !== undefined || b.dataset.returnSnack !== undefined) &&
    q?.game === "sharing" &&
    !trip.solved
  ) {
    const putting = b.dataset.share !== undefined,
      index = Number(putting ? b.dataset.share : b.dataset.returnSnack);
    trip.shares = changeShare(q, trip.shares, index, putting ? 1 : -1);
    trip.feedback = "";
    renderQuestion();
    const shareButton = document.querySelector(`[data-share="${index}"]`);
    (shareButton?.disabled ? $("#sharing-submit") : shareButton)?.focus({ preventScroll: pointerInteraction });
    announce(`第 ${index + 1} 位朋友有 ${trip.shares[index]} 份點心。`);
    return;
  }
  if (b.dataset.find !== undefined && q?.game === "treasure" && !trip.solved) {
    const index = Number(b.dataset.find);
    if (q.items[index] !== q.target) {
      trip.feedback = "這也是風景裡的小發現。再看看，我們要找題目中的寶物。";
      $(".feedback").textContent = trip.feedback;
      announce(trip.feedback);
      return;
    }
    trip.found.add(index);
    if (trip.found.size === q.answer) answer(q.answer);
    else {
      renderQuestion();
      document.querySelector("[data-find]:not(:disabled)")?.focus({ preventScroll: pointerInteraction });
      announce(`找到第 ${trip.found.size} 個寶物！`);
    }
    return;
  }
  if (b.dataset.load !== undefined && q?.game === "cargo" && !trip.solved) {
    const amount = Number(b.dataset.load);
    if (trip.cargo + amount <= q.max) trip.cargo += amount;
    trip.feedback = "";
    renderQuestion();
    const loadButton = document.querySelector(`[data-load="${amount}"]`);
    (loadButton?.disabled ? $("#cargo-submit") : loadButton)?.focus({ preventScroll: pointerInteraction });
    announce(`已裝 ${trip.cargo} 箱。`);
    return;
  }
  if (b.dataset.unload !== undefined && q?.game === "cargo" && !trip.solved) {
    trip.cargo = Math.max(0, trip.cargo - 1);
    trip.feedback = "";
    renderQuestion();
    document.querySelector("[data-load='1']")?.focus({ preventScroll: pointerInteraction });
    announce(`搬回一箱，現在 ${trip.cargo} 箱。`);
    return;
  }
  if (
    b.dataset.memory !== undefined &&
    q?.game === "memory" &&
    !trip.solved &&
    !trip.memoryPeek
  ) {
    const index = Number(b.dataset.memory);
    const before = trip.memory;
    trip.memory = memoryTurn(before, index, q.deck);
    if (before === trip.memory) return;
    if (trip.memory.matched.length === q.deck.length) answer(q.pairs.length);
    else {
      renderQuestion();
      if (trip.memory.open.length === 2) $("#memory-hide")?.focus({ preventScroll: pointerInteraction });
      else document.querySelector("[data-memory]:not(:disabled)")?.focus({ preventScroll: pointerInteraction });
      const t = byId(q.deck[index]);
      announce(
        `${t.cardLabel}${trip.memory.matched.length > before.matched.length ? "，找到一對！" : ""}`,
      );
      speak(t.cardLabel);
    }
    return;
  }
  switch (b.id) {
    case "program-run": {
      if (q?.game === "program" && trip.programRunning) { stopProgramRun(); renderQuestion(); }
      else startProgramRun();
      break;
    }
    case "program-reset":
      if (q?.game !== "program" || trip.solved) break;
      trip.workshop = newWorkshopState(q);
      trip.feedback = "";
      renderQuestion();
      document.querySelector("[data-program-direction]")?.focus({ preventScroll: pointerInteraction });
      break;
    case "balance-check": {
      if (q?.game !== "balance" || trip.solved) break;
      const total = weightTotal(q, trip.workshop.weights);
      if (total === null) break;
      Object.assign(trip.workshop, { balanceChecked: true, balanceTilt: total > q.target ? -1 : total < q.target ? 1 : 0 });
      answer(total);
      break;
    }
    case "balance-reset":
      if (q?.game !== "balance" || trip.solved) break;
      trip.workshop = newWorkshopState(q);
      trip.feedback = "";
      renderQuestion();
      document.querySelector("[data-balance-weight]")?.focus({ preventScroll: pointerInteraction });
      break;
    case "mosaic-submit":
      if (q?.game === "mosaic") answer(trip.discovery.mosaicCells);
      break;
    case "mosaic-reset":
      if (q?.game !== "mosaic" || trip.solved) break;
      trip.discovery = resetMosaic(q, trip.discovery);
      trip.feedback = "";
      renderQuestion();
      main.querySelector(".mosaic-paint-board").scrollTop = 0;
      document.querySelector("[data-mosaic-color]")?.focus({ preventScroll: pointerInteraction });
      break;
    case "journey-resume":
      resumeJourney();
      break;
    case "photo-retry":
      if (q && view === "game") { photoLoader.retry(gamePhotoPaths(q)); renderQuestion(); }
      break;
    case "tickets-check":
      if (q?.game === "tickets" && !trip.solved) {
        const totals = ticketTotals(q, trip.tickets.assignments);
        if (totals === null) break;
        trip.tickets = { ...trip.tickets, checked: true };
        answer(totals);
      }
      break;
    case "tickets-reset":
      if (q?.game !== "tickets" || trip.solved) break;
      trip.tickets = newTicketsState(q);
      trip.feedback = "";
      renderQuestion();
      document.querySelector("[data-ticket-pay]")?.focus({ preventScroll: pointerInteraction });
      break;
    case "lobby-start":
      practice = starterPractice(progress);
      selectedJourney = null;
      depart();
      break;
    case "quick-mixed":
      practice = "mixed";
      selectedJourney = null;
      depart();
      break;
    case "learning-read":
      speak(main.querySelector(".learning-discovery-text")?.textContent || "", true);
      break;
    case "quick-settings":
      settings();
      break;
    case "game-fullscreen":
      toggleGameFullscreen();
      break;
    case "arithmetic-keyboard":
      if (q?.game !== "boarding" || trip.solved) break;
      trip.nativeKeyboard = !trip.nativeKeyboard;
      renderQuestion();
      $("#boarding-input")?.focus({ preventScroll: pointerInteraction });
      break;
    case "puzzle-preview":
      if (q?.game !== "puzzle" || trip.solved) break;
      trip.puzzle = { ...trip.puzzle, preview: !trip.puzzle.preview };
      renderQuestion();
      $("#puzzle-preview")?.focus({ preventScroll: pointerInteraction });
      break;
    case "puzzle-reset":
      if (q?.game !== "puzzle" || trip.solved) break;
      trip.puzzle = newPuzzleState(q);
      trip.feedback = "";
      renderQuestion();
      document.querySelector("[data-puzzle-piece]")?.focus({ preventScroll: pointerInteraction });
      announce("拼圖片回到桌上，可以重新拼。");
      break;
    case "puzzle-submit":
      if (q?.game === "puzzle") answer(trip.puzzle.placements);
      break;
    case "luggage-submit":
      if (q?.game === "luggage") answer(trip.explorer.luggageAssignments);
      break;
    case "luggage-reset":
      if (q?.game !== "luggage" || trip.solved) break;
      trip.explorer = newExplorerState(q);
      trip.feedback = "";
      renderQuestion();
      document.querySelector("[data-luggage-item]")?.focus({ preventScroll: pointerInteraction });
      announce("行李回到月台了，可以重新分類。");
      break;
    case "maze-reset":
      if (q?.game !== "maze" || trip.solved) break;
      trip.explorer = newExplorerState(q);
      trip.feedback = "";
      renderQuestion();
      document.querySelector("[data-maze-direction]")?.focus({ preventScroll: pointerInteraction });
      announce("小火車回到起點了。");
      break;
    case "tracks-submit":
      if (q?.game === "tracks")
        answer(
          trackConnected(q, trip.rotations) ? "connected" : "disconnected",
        );
      break;
    case "tracks-reset":
      if (q?.game !== "tracks" || trip.solved) break;
      trip.rotations = q.tiles.map((tile) => tile.initial);
      trip.feedback = "";
      renderQuestion();
      document.querySelector("[data-rotate]:not(:disabled)")?.focus({ preventScroll: pointerInteraction });
      break;
    case "sharing-submit":
      if (q?.game === "sharing") answer(trip.shares);
      break;
    case "sharing-reset":
      if (q?.game !== "sharing" || trip.solved) break;
      trip.shares = Array(q.friends).fill(0);
      trip.feedback = "";
      renderQuestion();
      document.querySelector("[data-share]")?.focus({ preventScroll: pointerInteraction });
      announce("點心都放回籃子了。");
      break;
    case "gift-open":
      if (!progress.giftCredits || trip?.gift) break;
      const choices = offerGifts(progress, trip?.train.id || selected);
      persist();
      if (trip?.awarded && $("#trip-gift")) {
        trip.giftChoices = choices;
        $("#trip-gift").innerHTML = souvenirMarkup(trip, { esc });
      } else renderStamps();
      document.querySelector("[data-gift-choice]")?.focus({ preventScroll: pointerInteraction });
      announce("選一份喜歡的小禮物收藏吧。");
      break;
    case "trip-start":
    case "map-depart":
      depart();
      break;
    case "trip-again":
      startTrip();
      break;
    case "trip-new": {
      const current = trip?.train;
      const candidates = photoGameTrains(trains).filter(t => !current || !samePhotoIdentity(t, { ...displayTrain(current), image: trainImage(current) }));
      const unseen = candidates.filter(t => !progress.completed.includes(t.id));
      const pool = unseen.length ? unseen : candidates;
      if (pool.length) selected = pool[Math.floor(Math.random() * pool.length)].id;
      practice = "mixed";
      selectedJourney = null;
      startTrip();
      break;
    }
    case "trip-exit":
      pauseTrip();
      location.hash = "#playroom";
      route();
      break;
    case "hint-show":
      hint();
      break;
    case "question-replay":
      const spokenQuestion = trip?.questions[trip.index];
      speak(spokenQuestionText(spokenQuestion), true);
      break;
    case "question-next":
      next();
      break;
    case "order-submit":
      answer(trip.order);
      break;
    case "order-reset":
      trip.order = [];
      trip.feedback = "";
      renderQuestion();
      break;
    case "cargo-submit":
      if (q?.game === "cargo") answer(trip.cargo);
      break;
    case "cargo-reset":
      if (q?.game !== "cargo" || trip.solved) break;
      trip.cargo = 0;
      trip.feedback = "";
      renderQuestion();
      document.querySelector("[data-load='1']")?.focus({ preventScroll: pointerInteraction });
      announce("貨物已全部搬回。現在零箱。");
      break;
    case "memory-hide":
      if (q?.game !== "memory" || trip.solved) break;
      trip.memoryPeek = false;
      trip.memory = { ...trip.memory, open: [] };
      renderQuestion();
      document.querySelector("[data-memory]:not(:disabled)")?.focus({ preventScroll: pointerInteraction });
      break;
    case "station-bell":
      chime();
      announce(
        progress.effects ? "叮咚，列車即將進站。" : "進站鈴音效已關閉。",
      );
      break;
    case "settings-open":
      settings();
      break;
    case "sound-toggle":
      progress.voice = !progress.voice;
      persist();
      applyPreferences();
      if (progress.voice) speak("語音已開啟。小小列車長，準備出發！");
      else cancelVoice();
      break;
    case "about-open":
      storyHandle?.pause();
      $("#about-dialog").showModal();
      break;
    case "clear-progress":
      $("#clear-confirm").innerHTML =
        '<p>確定要清除所有本機紀錄嗎？</p><button id="clear-yes" class="danger-btn">確定清除</button><button id="clear-no" class="secondary-btn">保留紀錄</button>';
      break;
    case "clear-no":
      $("#clear-confirm").innerHTML = "";
      break;
    case "clear-yes":
      progress = defaults();
      trip = null;
      pausedTrip = null;
      clearTripSession(tripStorage);
      try {
        storage.removeItem(STORAGE_KEY);
      } catch {}
      persist();
      applyPreferences();
      $("#settings-dialog").close();
      route();
      announce("本機紀錄已清除。");
      break;
  }
});
for (const [eventName, status] of [["load", "ready"], ["error", "error"]]) document.addEventListener(eventName, event => {
  const picture = event.target;
  if (picture.tagName !== "IMG" || (!main.contains(picture) && !$("#detail-content").contains(picture))) return;
  const source = picture.getAttribute("src");
  if (!/^assets\/images\//.test(source || "")) return;
  photoLoader.report(source, status);
  const owner = picture.closest(".train-card") || picture.closest("#detail-content");
  const retry = owner?.querySelector("[data-train-photo-retry]");
  if (retry) retry.hidden = status !== "error";
}, true);
document.addEventListener("input", (event) => {
  if (event.target.id === "boarding-input" && trip && !trip.solved) {
    trip.boardingInput = event.target.value;
  }
  if (event.target.id === "train-search") {
    search = event.target.value;
    renderCards();
  }
});
document.addEventListener("submit", (event) => {
  if (event.target.id !== "boarding-form") return;
  event.preventDefault();
  submitArithmetic();
});
attachPuzzleTouch(main, {
  onDrop(pieceId, slot) {
    const q = trip?.questions[trip.index];
    if (q?.game !== "puzzle" || trip.solved) return;
    const selectedState = selectPuzzlePiece(q, { ...trip.puzzle, selectedPiece: null }, pieceId);
    trip.puzzle = placePuzzlePiece(q, selectedState, slot);
    renderQuestion();
    document.querySelector(`[data-puzzle-slot="${slot}"]`)?.focus({ preventScroll: true });
    announce("拼圖片放好了，再看看線條有沒有接起來。");
  },
  onAnnounce: announce,
});
document.addEventListener("keydown", (event) => {
  const categoryTab = event.target.closest?.("[data-game-category]");
  if (view === "playroom" && categoryTab && !event.altKey && !event.ctrlKey && !event.metaKey && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    const tabs = [...main.querySelectorAll("[data-game-category]")], at = tabs.indexOf(categoryTab);
    const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (at + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    changeGameCategory(tabs[next].dataset.gameCategory);
    return;
  }
  const directions = { ArrowUp: "up", ArrowRight: "right", ArrowDown: "down", ArrowLeft: "left" };
  const direction = Object.hasOwn(directions, event.key) ? directions[event.key] : null;
  const q = trip?.questions[trip.index];
  if (view !== "game" || !q) return;
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  if (document.querySelector("dialog[open]") || /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
  if (q.game === "program" && event.key === "Enter" && event.repeat) { event.preventDefault(); return; }
  if (trip.solved) return;
  if (q.game === "program") {
    if (direction) {
      event.preventDefault();
      if (event.repeat || trip.programRunning) return;
      trip.workshop = appendCommand(q, trip.workshop, direction);
      trip.feedback = "";
      renderQuestion();
      const queue = main.querySelector(".program-queue");
      if (queue) queue.scrollLeft = queue.scrollWidth;
      main.focus({ preventScroll: true });
      return;
    }
    if (event.key === "Enter" && (event.target === main || event.target === document.body)) {
      event.preventDefault();
      if (event.repeat) return;
      if (trip.programRunning) { stopProgramRun(); renderQuestion(); }
      else startProgramRun();
    }
    return;
  }
  if (!direction || q.game !== "maze") return;
  event.preventDefault();
  stepMaze(direction);
});
document.addEventListener("change", (event) => {
  if (event.target.id === "practice-select") {
    practice = event.target.value;
    selectedJourney = null;
    renderHome();
    $("#practice-select")?.focus({ preventScroll: pointerInteraction });
  }
  if (event.target.dataset.pref) {
    progress[event.target.dataset.pref] = event.target.checked;
    persist();
    applyPreferences();
    if (event.target.dataset.pref === "voice" && !progress.voice) cancelVoice();
  }
});
for (const d of document.querySelectorAll("dialog"))
  d.addEventListener("click", (e) => {
    if (e.target === d) d.close();
  });
window.addEventListener("hashchange", route);
window.addEventListener("pagehide", () => {
  stopProgramRun();
  saveCurrentTrip();
  cancelVoice();
  storyHandle?.pause();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) return;
  const programWasRunning = Boolean(activeProgramRun);
  stopProgramRun();
  if (programWasRunning && view === "game" && trip) renderQuestion();
  saveCurrentTrip();
  cancelVoice();
  storyHandle?.pause();
  if (audioContext?.state === "running") audioContext.suspend().catch(() => {});
});
function updateFullscreenControl() {
  const button = $("#game-fullscreen");
  if (!button) return;
  const active = Boolean(document.fullscreenElement || document.webkitFullscreenElement);
  button.setAttribute("aria-pressed", String(active));
  button.setAttribute("aria-label", active ? "離開全螢幕" : "放大遊戲畫面");
}
document.addEventListener("fullscreenchange", updateFullscreenControl);
document.addEventListener("webkitfullscreenchange", updateFullscreenControl);
function syncKeyboardDock() {
  const viewport = window.visualViewport;
  const input = document.activeElement;
  const editing = viewport && input?.id === "boarding-input" && !input.readOnly && viewport.scale <= 1.01;
  const inset = editing ? Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop) : 0;
  document.documentElement.style.setProperty("--keyboard-inset", `${inset}px`);
}
window.visualViewport?.addEventListener("resize", syncKeyboardDock);
window.visualViewport?.addEventListener("scroll", syncKeyboardDock);
document.addEventListener("focusin", syncKeyboardDock);
document.addEventListener("focusout", () => requestAnimationFrame(syncKeyboardDock));
motionPreference.addEventListener("change", applyPreferences);
try {
  const controller = new AbortController();
  const deadline = setTimeout(() => controller.abort(), 15000);
  let response;
  try { response = await fetch("data/trains.json?v=1.10.1", { signal: controller.signal }); }
  finally { clearTimeout(deadline); }
  if (!response.ok) throw new Error("Content unavailable");
  catalogue = await response.json();
  trains = catalogue.trains;
  pausedTrip = readTripSession(tripStorage, { trains });
  route();
} catch (error) {
  main.innerHTML =
    '<div class="loading"><h1>列車資料還沒載入</h1><p>請確認網路連線，再重新整理。若在電腦開啟檔案，請先依 README 啟動本機伺服器。</p><button onclick="location.reload()" class="primary-btn">重新載入</button></div>';
  console.error(error);
}
