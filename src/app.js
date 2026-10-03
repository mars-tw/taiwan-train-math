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
} from "./engine.js?v=1.1.0";
import { homeMarkup } from "./home.js?v=1.1.0";
import { activityScene, patternToken, patternName } from "./activities.js?v=1.1.0";

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
let catalogue,
  trains = [],
  progress,
  trip = null,
  view = "home",
  filter = "all",
  search = "",
  selected = "700t",
  practice = "mixed",
  mood = "golden",
  departureToken = null,
  audioContext;
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
const byId = (id) => trains.find((t) => t.id === id);
let storage;
try {
  storage = localStorage;
} catch {
  storage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
}
progress = readProgress(storage);
function persist() {
  if (!saveProgress(storage, progress))
    announce("這台裝置無法儲存進度，但還是可以繼續玩。");
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
function chime() {
  if (!progress.effects) return;
  try {
    audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
    audioContext.resume();
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
function image(t, cls = "", lazy = true) {
  return `<img class="${cls}" src="${esc(t.image)}" alt="${esc(t.name)}的電影風情境插圖" ${lazy ? 'loading="lazy"' : 'fetchpriority="high"'} width="1200" height="675">`;
}
function tag(t) {
  return `<span class="tag ${t.category}">${esc(t.tag || labels[t.category])}</span>`;
}
function artNote(t) {
  return t.imageKind === "family" ? "車型家族情境示意" : "電影風情境插圖";
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
  return `<article class="train-card ${selected === t.id ? "chosen" : ""}"><button class="train-picture" data-select="${t.id}" aria-label="選擇${esc(t.cardLabel)}" aria-pressed="${selected === t.id}">${image(t)}${tag(t)}${selected === t.id ? '<span class="chosen-label">✓ 本次列車</span>' : ""}</button><div class="train-card-body"><div><h3>${esc(t.name)}</h3><p>${esc(t.model)}</p></div><button class="info-btn" data-detail="${t.id}" aria-label="認識${esc(t.cardLabel)}">↗</button></div><small class="art-note">${artNote(t)}</small></article>`;
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
        [t.name, t.model, t.operator, t.cardLabel]
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
  main.innerHTML = homeMarkup({
    trains,
    selected,
    progress,
    practice,
    mood,
    esc,
    image,
    levelButtons,
  });
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
    view !== "home" ||
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
    if (departureToken === token && view === "home") startTrip();
  }, 420);
}
function chooseMission(id, source) {
  if (!allowedGames(progress.level).includes(id)) {
    const message = `${GAMES[id].name}適合 5–8 歲。可以先選「火車助手」或「小小列車長」，再來玩這個任務。`;
    $("#home-notice").textContent = message;
    $("#age-note").textContent = message;
    announce(message);
    speak(message);
    const suggested = document.querySelector("[data-level='medium']");
    suggested?.setAttribute("aria-describedby", "age-note");
    suggested?.focus();
    return;
  }
  practice = id;
  if (source === "mission") {
    depart();
    return;
  }
  renderHome();
  document.querySelector(`[data-${source}="${id}"]`)?.focus();
  const message = `已選擇${GAMES[id].name}。搭 ${byId(selected).cardLabel} 出發！`;
  announce(message);
  speak(message);
}
function renderCollection() {
  main.innerHTML = `<div class="content-wrap catalogue-page"><div class="page-intro"><div class="eyebrow dark">THE TRAIN ENCYCLOPEDIA</div><h1>火車圖鑑</h1><p>每一台列車，都有自己的名字。點圖片選車，點箭頭聽聽它的故事。</p><span class="catalogue-note">台灣列車・林鐵與觀光名稱・海外子彈列車・磁浮試驗列車</span></div>${filterBar()}<div class="collection-toolbar"><span id="result-count"></span><a href="#home" class="text-link">選好了，回去出發 →</a></div><div id="train-grid" class="train-grid"></div><p class="fineprint">插圖呈現列車與風景的情境，部分使用車型家族示意。名稱、型號與來源請見各列車介紹。</p></div>`;
  renderCards();
}
function renderStamps() {
  const completed = progress.completed.map(byId).filter(Boolean);
  main.innerHTML = `<div class="content-wrap stamps-page"><div class="page-intro"><div class="eyebrow dark">MY RAILWAY PASSPORT</div><h1>我的鐵道護照</h1><p>已完成 <strong>${progress.trips}</strong> 趟旅程，留下 <strong>${completed.length}</strong> 款列車的紀念章。</p></div>${completed.length ? `<div class="stamp-grid">${completed.map((t) => `<button class="stamp-card" data-detail="${t.id}"><div class="stamp-image">${image(t)}<span aria-hidden="true">✦</span></div><strong>${esc(t.name)}</strong><small>${esc(t.model)}</small><span class="stamp-seal">旅程完成 ✓</span></button>`).join("")}</div>` : '<div class="empty-passport"><span aria-hidden="true">🎟</span><h2>你的第一枚紀念章在等你</h2><p>選一台喜歡的火車，完成一趟小旅程就能收藏。</p><a href="#home" class="primary-btn">出發旅行 →</a></div>'}<p class="fineprint">護照存在這台裝置；清除瀏覽器資料會一起清除。所有列車都能自由選擇。</p></div>`;
}
function route() {
  cancelVoice();
  clearDeparture();
  const hash = location.hash.slice(1);
  if (hash === "departure" && view === "home" && $("#departure")) {
    return;
  }
  view = ["collection", "stamps"].includes(hash) ? hash : "home";
  trip = null;
  document
    .querySelectorAll("[data-nav]")
    .forEach((n) => n.classList.toggle("current", n.dataset.nav === view));
  if (view === "collection") renderCollection();
  else if (view === "stamps") renderStamps();
  else renderHome();
  applyPreferences();
  if (hash === "departure")
    $("#departure")?.scrollIntoView({ behavior: "instant" });
}
function detail(id) {
  const t = byId(id);
  if (!t) return;
  $("#detail-content").innerHTML =
    `<form method="dialog" class="detail-top"><button class="close-btn" aria-label="關閉列車介紹">×</button></form>${image(t, "detail-image", false)}<div class="detail-body">${tag(t)}<h2 id="detail-title">${esc(t.name)}</h2><div class="model-badge">${esc(t.model)} <small>${t.modelKind === "type" ? "型號" : t.modelKind === "fleet" ? "車號系列" : "列車名稱／編組說明"}</small></div><p>${esc(t.intro)}</p><p class="train-fact">${esc(t.fact)}</p><div class="detail-actions"><button class="secondary-btn" data-speak="${t.id}">♪ 聽聽名字</button><button class="primary-btn" data-travel="${t.id}">搭這台出發 →</button></div><div class="detail-source"><small>${artNote(t)}・${esc(t.operator)}<br>${esc(t.note || "列車名稱與型號是教材資料；圖片細節以實車為準。")}</small><a href="${esc(t.sources[0])}" target="_blank" rel="noopener">資料來源 ↗</a></div></div>`;
  $("#detail-dialog").showModal();
}
function settings() {
  cancelVoice();
  clearDeparture();
  $("#settings-content").innerHTML =
    `<p>按孩子的理解程度選難度，隨時都能更換。</p><div class="settings-levels">${levelButtons()}</div><label class="setting-row"><span><strong>中文語音</strong><small>${"speechSynthesis" in window ? "使用這台裝置的中文語音" : "這台裝置沒有語音服務，仍可使用畫面提示"}</small></span><input type="checkbox" data-pref="voice" ${progress.voice ? "checked" : ""} ${"speechSynthesis" in window ? "" : "disabled"}></label><label class="setting-row"><span><strong>柔和音效</strong><small>完成任務時的小小慶祝</small></span><input type="checkbox" data-pref="effects" ${progress.effects ? "checked" : ""}></label><label class="setting-row"><span><strong>減少動畫</strong><small>讓畫面更加平靜</small></span><input type="checkbox" data-pref="reduceMotion" ${progress.reduceMotion ? "checked" : ""}></label><label class="setting-row"><span><strong>跨十加減挑戰</strong><small>只在 7–8 歲模式啟用</small></span><input type="checkbox" data-pref="challenge" ${progress.challenge ? "checked" : ""}></label><div class="clear-record"><button id="clear-progress" class="danger-btn">清除本機紀錄</button><p>只會清除這台裝置的護照與設定。</p><div id="clear-confirm"></div></div>`;
  $("#settings-dialog").showModal();
}
function startTrip() {
  clearDeparture();
  cancelVoice();
  view = "game";
  const train = byId(selected);
  trip = {
    train,
    questions: createTrip({
      level: progress.level,
      train,
      trains,
      challenge: progress.challenge,
      practice,
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
    boardingPhase: "before",
    feedback: "",
  };
  renderQuestion();
  speak(`${train.intro} ${trip.questions[0].prompt}`);
  main.focus();
  window.scrollTo({ top: 0, behavior: "instant" });
}
function dotCard(n) {
  return n === 0
    ? '<span class="zero-dots">沒有</span>'
    : `<span class="dot-card" aria-label="${n} 個點">${Array.from({ length: n }, () => "<i></i>").join("")}</span>`;
}
const person = (i, clicked = false, extra = "") =>
  `<svg viewBox="0 0 48 60" aria-hidden="true" class="person-svg ${extra}"><circle cx="24" cy="12" r="9" fill="${["#e6b08d", "#bf886d", "#d5a383"][i % 3]}"/><path d="M15 11q0-15 18-4v6q-3-9-18-2" fill="#343d40"/><rect x="12" y="24" width="24" height="24" rx="9" fill="${clicked ? "#1c7e70" : ["#eeaa64", "#698b93", "#a6a081", "#ac817a"][i % 4]}"/><path d="M18 47v9m12-9v9" stroke="#334b54" stroke-width="7" stroke-linecap="round"/>${clicked ? '<path d="M18 35l4 4 9-10" fill="none" stroke="white" stroke-width="3"/>' : ""}</svg>`;
function passengers(count, { interactive = false, changed = 0 } = {}) {
  return count === 0
    ? '<div class="no-passengers">月台還沒有人 <span aria-hidden="true">○</span></div>'
    : `<div class="passengers ${count > 10 ? "many" : ""}">${Array.from({ length: count }, (_, i) => (interactive ? `<button class="person ${trip.counted.has(i) ? "counted" : ""}" data-count="${i}" aria-label="第 ${i + 1} 位乘客${trip.counted.has(i) ? "，已點過" : ""}" aria-pressed="${trip.counted.has(i)}">${person(i, trip.counted.has(i))}<span>${trip.counted.has(i) ? [...trip.counted].indexOf(i) + 1 : ""}</span></button>` : `<span class="person ${i >= count - changed ? "arrived" : ""}">${person(i, false)}</span>`)).join("")}</div>`;
}
function ticketPile(n) {
  return `<div class="ticket-pile">${Array.from({ length: n }, () => '<span class="tiny-ticket" aria-hidden="true">🎟</span>').join("")}</div>`;
}
function gameScene(q) {
  if (["pattern", "cargo", "memory", "clock"].includes(q.game))
    return activityScene(q, trip, { byId, image, esc });
  if (q.game === "count")
    return `<div class="stage-label">安全月台 · 一位乘客點一次</div>${passengers(q.count, { interactive: true })}<div class="count-status">${trip.counted.size ? `已經點過 ${trip.counted.size} 位乘客` : "點點乘客，一起數一數"}</div>`;
  if (q.game === "identify")
    return '<div class="identify-intro"><span aria-hidden="true">🚆</span><p>仔細看看列車卡，<br>找到它的名字。</p></div>';
  if (q.game === "compare")
    return `<div class="compare-stage"><div><span class="stage-label">左邊的車票</span>${ticketPile(q.left)}</div><div><span class="stage-label">右邊的車票</span>${ticketPile(q.right)}</div></div>`;
  if (q.game === "boarding") {
    const after = trip.boardingPhase === "after";
    const count = after ? q.answer : q.start;
    return `<div class="boarding-stage"><span class="stage-label">${after ? "變化完成，數數現在的乘客" : "看看原本車上的乘客"}</span>${passengers(count, { changed: after && q.operation === "add" ? q.change : 0 })}<div class="math-equation">${q.start} <span>${q.operation === "add" ? "＋" : "−"}</span> ${q.change} <span>＝</span> ${trip.solved ? q.answer : "？"}</div><button class="secondary-btn" id="boarding-play" ${trip.boardingPhase === "moving" ? "disabled" : ""}>${trip.boardingPhase === "moving" ? "乘客正在移動……" : after ? "↺ 再看一次" : q.operation === "add" ? `讓 ${q.change} 位乘客上車 →` : `讓 ${q.change} 位乘客下車 →`}</button></div>`;
  }
  if (q.game === "order")
    return `<div class="sorting-stage"><span class="stage-label">數學示意列車 · 點一下就能排車廂</span><div class="sorting-track"><span class="toy-engine" aria-label="示意列車車頭">🚂</span>${q.answer.map((_, i) => `<button class="carriage-slot ${trip.order[i] !== undefined ? "filled" : ""}" data-remove-order="${i}" ${trip.solved ? "disabled" : ""} aria-label="第 ${i + 1} 節${trip.order[i] !== undefined ? `，數字 ${trip.order[i]}，點選移除` : "，空車廂"}">${trip.order[i] ?? "?"}</button>`).join("")}</div><div class="sorting-bank">${q.numbers.map((n) => `<button class="number-carriage" data-order="${n}" ${trip.order.includes(n) || trip.solved ? "disabled" : ""} aria-label="放入數字 ${n}">${n}</button>`).join("")}</div><div class="sort-actions"><button class="text-btn" id="order-reset" ${trip.solved ? "disabled" : ""}>重新排一次</button><button class="primary-btn" id="order-submit" ${trip.order.length !== q.answer.length || trip.solved ? "disabled" : ""}>排好了 ✓</button></div></div>`;
  return "";
}
function answerMarkup(q) {
  if (["order", "cargo", "memory"].includes(q.game)) return "";
  return `<div class="answers ${q.game === "identify" ? "picture-answers" : ""}">${q.choices
    .map((value) => {
      const disabled =
        trip.solved ||
        (q.game === "boarding" && trip.boardingPhase !== "after");
      if (q.game === "identify") {
        const t = byId(value);
        return `<button class="answer-card" data-answer="${value}" ${disabled ? "disabled" : ""}>${image(t)}<strong>${esc(t.name)}</strong><small>${esc(t.model)}</small></button>`;
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
function renderQuestion() {
  if (!trip) return;
  const q = trip.questions[trip.index];
  main.innerHTML = `<div class="game-wrap"><div class="game-top"><button id="trip-exit" class="text-btn">← 返回選車</button><span>${LEVELS[q.level].name} · ${gameLabels[q.game]}</span><button id="question-replay" class="secondary-btn">♪ 聽題目</button></div><div class="trip-progress" aria-label="第 ${trip.index + 1} 站，共 ${trip.questions.length} 站">${trip.questions.map((_, i) => `<span class="progress-stop ${i < trip.index ? "done" : ""} ${i === trip.index ? "current" : ""}"><i>${i < trip.index ? "✓" : i + 1}</i><small>${["城市站", "山林站", "海邊站", "田野站", "終點站"][i]}</small></span>`).join("")}</div><section class="game-panel"><div class="question-head"><span class="question-icon" aria-hidden="true">${gameIcons[q.game]}</span><h1 id="question-title">${esc(q.prompt)}</h1></div><div class="game-stage" id="game-stage">${gameScene(q)}</div>${answerMarkup(q)}<div class="feedback ${trip.solved ? "success" : ""}" role="status" aria-live="polite">${esc(trip.feedback || "慢慢來，想一想也沒關係。")}</div><div class="question-actions"><button id="hint-show" class="text-btn" ${trip.solved ? "disabled" : ""}>☀ 一起想一想</button>${trip.solved ? `<button id="question-next" class="primary-btn">${trip.index === trip.questions.length - 1 ? "抵達終點，收集紀念章" : "前往下一站"} →</button>` : ""}</div></section><div class="trip-train-note">${image(trip.train)}<span><strong>${esc(trip.train.name)}</strong><small>${esc(trip.train.model)} · 今天一起旅行的列車</small></span><button data-speak="${trip.train.id}" class="icon-btn" aria-label="聽今天的列車名字">♪</button></div></div>`;
}
function answer(value) {
  if (!trip || trip.solved) return;
  const q = trip.questions[trip.index];
  if (q.game === "boarding" && trip.boardingPhase !== "after") return;
  if (isCorrect(q, value)) {
    trip.solved = true;
    trip.feedback = trip.assisted
      ? "一起完成了！可以去下一站囉。"
      : "完成了！準備好去下一站囉。";
    chime();
    speak(trip.feedback);
    renderQuestion();
    $("#question-next")?.focus();
  } else {
    trip.attempts++;
    trip.feedback = trip.attempts >= 2 ? q.hint : "再看看，我們一起想一想。";
    if (trip.attempts >= 2) trip.assisted = true;
    speak(trip.feedback);
    renderQuestion();
  }
}
function hint() {
  if (!trip || trip.solved) return;
  const q = trip.questions[trip.index];
  trip.assisted = true;
  trip.feedback = q.hint;
  if (q.game === "count")
    trip.counted = new Set(Array.from({ length: q.count }, (_, i) => i));
  if (q.game === "order")
    trip.feedback = `${q.hint} 小提示：${q.answer.join("、")}。`;
  if (q.game === "memory") trip.memoryPeek = true;
  renderQuestion();
  speak(trip.feedback);
}
function boarding() {
  if (!trip || trip.solved || trip.boardingPhase === "moving") return;
  const activeTrip = trip;
  trip.boardingPhase = "moving";
  renderQuestion();
  cancelVoice();
  setTimeout(
    () => {
      if (trip !== activeTrip || view !== "game") return;
      trip.boardingPhase = "after";
      renderQuestion();
      announce("乘客移動完成，現在可以選答案。");
    },
    progress.reduceMotion ? 0 : 650,
  );
}
function next() {
  if (!trip?.solved) return;
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
      boardingPhase: "before",
      feedback: "",
    });
    renderQuestion();
    speak(trip.questions[trip.index].prompt);
    $("#question-title").setAttribute("tabindex", "-1");
    $("#question-title").focus();
  } else finishTrip();
}
function finishTrip() {
  if (!trip) return;
  if (!trip.awarded) {
    trip.awarded = true;
    progress.trips++;
    if (!progress.completed.includes(trip.train.id))
      progress.completed.push(trip.train.id);
    persist();
  }
  const t = trip.train;
  main.innerHTML = `<div class="finish-wrap"><div class="eyebrow dark">JOURNEY COMPLETED</div><h1>抵達終點，做得好！</h1><p>每一次發現，都值得一枚紀念章。</p><div class="finish-stamp">${image(t, "", false)}<span class="finish-stars" aria-hidden="true">✦</span><h2>${esc(t.name)}</h2><p>${esc(t.model)}</p><div class="stamp-seal">我的鐵道旅程 · 完成 ✓</div></div><p class="finish-note">今天認識了${esc(t.name)}。下次再一起出發吧！</p><div class="finish-actions"><button id="trip-again" class="primary-btn">再坐一趟 →</button><a href="#stamps" class="secondary-btn">看看我的集章</a><a href="#home" class="text-btn">休息一下</a></div></div>`;
  speak(`抵達終點，做得好！今天一起搭乘了${t.name}。`);
  main.focus();
}
document.addEventListener("click", (event) => {
  const nav = event.target.closest('a[href^="#"]');
  if (nav?.getAttribute("href") === "#main") {
    event.preventDefault();
    main.focus();
    main.scrollIntoView({ behavior: "instant" });
    return;
  }
  if (
    nav &&
    ["#home", "#collection", "#stamps"].includes(nav.getAttribute("href")) &&
    location.hash === nav.getAttribute("href")
  ) {
    event.preventDefault();
    route();
    window.scrollTo({ top: 0, behavior: "instant" });
    return;
  }
  const b = event.target.closest("button");
  if (!b) return;
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
    if (view === "home") {
      renderHome();
      if (!$("#settings-dialog").open)
        document.querySelector(`[data-level="${progress.level}"]`)?.focus();
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
    else renderCards();
    const t = byId(selected);
    if ($("#selected-name")) $("#selected-name").textContent = t.cardLabel;
    speak(t.intro);
    announce(`已選擇${t.cardLabel}`);
    document.querySelector(`[data-select="${selected}"]`)?.focus();
    return;
  }
  if (b.dataset.detail) {
    detail(b.dataset.detail);
    return;
  }
  if (b.dataset.speak) {
    speak(byId(b.dataset.speak)?.intro || "", true);
    return;
  }
  if (b.dataset.travel) {
    selected = b.dataset.travel;
    $("#detail-dialog").close();
    practice = "mixed";
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
  if (b.dataset.count !== undefined && trip && !trip.solved) {
    const i = Number(b.dataset.count);
    if (!trip.counted.has(i)) {
      trip.counted.add(i);
      speak(String(trip.counted.size));
      $("#game-stage").innerHTML = gameScene(trip.questions[trip.index]);
    }
    return;
  }
  if (b.dataset.order !== undefined && trip && !trip.solved) {
    const n = Number(b.dataset.order);
    if (!trip.order.includes(n)) trip.order.push(n);
    renderQuestion();
    return;
  }
  if (b.dataset.removeOrder !== undefined && trip && !trip.solved) {
    trip.order.splice(Number(b.dataset.removeOrder), 1);
    renderQuestion();
    return;
  }
  if (b.dataset.mood) {
    mood = b.dataset.mood;
    renderHome();
    document.querySelector(`[data-mood="${mood}"]`)?.focus();
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
  const q = trip?.questions[trip.index];
  if (b.dataset.load !== undefined && q?.game === "cargo" && !trip.solved) {
    const amount = Number(b.dataset.load);
    if (trip.cargo + amount <= q.max) trip.cargo += amount;
    renderQuestion();
    const loadButton = document.querySelector(`[data-load="${amount}"]`);
    (loadButton?.disabled ? $("#cargo-submit") : loadButton)?.focus();
    announce(`已裝 ${trip.cargo} 箱。`);
    return;
  }
  if (b.dataset.unload !== undefined && q?.game === "cargo" && !trip.solved) {
    trip.cargo = Math.max(0, trip.cargo - 1);
    renderQuestion();
    document.querySelector("[data-load='1']")?.focus();
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
      if (trip.memory.open.length === 2) $("#memory-hide")?.focus();
      else document.querySelector("[data-memory]:not(:disabled)")?.focus();
      const t = byId(q.deck[index]);
      announce(
        `${t.cardLabel}${trip.memory.matched.length > before.matched.length ? "，找到一對！" : ""}`,
      );
      speak(t.cardLabel);
    }
    return;
  }
  switch (b.id) {
    case "trip-start":
    case "map-depart":
      depart();
      break;
    case "trip-again":
      startTrip();
      break;
    case "trip-exit":
      location.hash = "#home";
      view = "home";
      route();
      break;
    case "hint-show":
      hint();
      break;
    case "question-replay":
      speak(trip?.questions[trip.index].prompt || "", true);
      break;
    case "question-next":
      next();
      break;
    case "boarding-play":
      boarding();
      break;
    case "order-submit":
      answer(trip.order);
      break;
    case "order-reset":
      trip.order = [];
      renderQuestion();
      break;
    case "cargo-submit":
      if (q?.game === "cargo") answer(trip.cargo);
      break;
    case "cargo-reset":
      if (q?.game !== "cargo" || trip.solved) break;
      trip.cargo = 0;
      renderQuestion();
      document.querySelector("[data-load='1']")?.focus();
      announce("貨物已全部搬回。現在零箱。");
      break;
    case "memory-hide":
      if (q?.game !== "memory" || trip.solved) break;
      trip.memoryPeek = false;
      trip.memory = { ...trip.memory, open: [] };
      renderQuestion();
      document.querySelector("[data-memory]:not(:disabled)")?.focus();
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
document.addEventListener("input", (event) => {
  if (event.target.id === "train-search") {
    search = event.target.value;
    renderCards();
  }
});
document.addEventListener("change", (event) => {
  if (event.target.id === "practice-select") {
    practice = event.target.value;
    renderHome();
    $("#practice-select")?.focus();
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
try {
  const response = await fetch("data/trains.json");
  if (!response.ok) throw new Error("Content unavailable");
  catalogue = await response.json();
  trains = catalogue.trains;
  route();
} catch (error) {
  main.innerHTML =
    '<div class="loading"><h1>列車資料還沒載入</h1><p>請確認網路連線，再重新整理。若在電腦開啟檔案，請先依 README 啟動本機伺服器。</p><button onclick="location.reload()" class="primary-btn">重新載入</button></div>';
  console.error(error);
}
