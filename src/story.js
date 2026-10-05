import {
  CHAPTERS,
  STORY_DURATION,
  newStoryState,
  storyProgress,
  storyChapter,
  advanceStory,
  goToChapter,
} from "./story-model.js?v=1.8.1";
export { newStoryState };
export function storyMarkup() {
  return `<section class="story-scene" id="story-scene" aria-labelledby="story-title">
    <img class="story-landscape" src="assets/images/story-coast-v3.webp" alt="電影風想像山海鐵道，軌道由山林延伸到海邊" width="1672" height="941" fetchpriority="high" decoding="async"><div class="story-vignette"></div>
    <div class="story-atmosphere" aria-hidden="true"><i></i><i></i><i></i></div>
    <div class="story-train" id="story-train"><img src="assets/images/star-express-v3.webp" alt="星光高鐵，白色與金橘色的想像故事列車，車頭朝畫面下方" width="1024" height="1536" fetchpriority="high" decoding="async"><span class="train-headlight" aria-hidden="true"></span></div>
    <div class="story-copy"><div class="eyebrow">INTERACTIVE RAILWAY STORY · 01</div><h1 id="story-title">搭上星光高鐵，<br>把驚喜送到<span>下一站。</span></h1><p>看列車緩緩往下走，<br>點點風景，發現旅途的小秘密。</p><div class="story-controls"><button id="story-toggle" class="story-action">Ⅱ 暫停故事</button><button id="story-next" class="story-action">下一段 →</button><button id="story-replay" class="story-icon" aria-label="重播星光高鐵故事">↺</button></div><small id="story-motion-note"></small><a href="#railway-map" class="story-map-link">直接選車玩遊戲 ↓</a></div>
    <div class="story-discoveries" role="group" aria-label="故事風景中的小驚喜"><button data-discover="bird" class="scenic-surprise surprise-bird" aria-label="叫醒山谷的小鳥" aria-pressed="false"><span aria-hidden="true">🐦</span><small>小鳥在說什麼？</small></button><button data-discover="light" class="scenic-surprise surprise-light" aria-label="點亮海邊燈塔" aria-pressed="false"><span aria-hidden="true">☀</span><small>點亮燈塔</small></button><button data-discover="letter" class="scenic-surprise surprise-letter" aria-label="看看星光信封" aria-pressed="false"><span aria-hidden="true">✉</span><small>信裡有小秘密</small></button></div>
    <div class="story-narrative"><div class="story-kicker"><span>星光高鐵 · <b id="story-place"></b></span><button id="story-read" aria-label="朗讀這一段故事">♪ 聽故事</button></div><div id="story-caption" aria-live="polite"><h2></h2><p></p></div><div class="story-chapters" role="group" aria-label="四段故事，可直接選擇">${CHAPTERS.map((c, i) => `<button data-chapter="${i}" aria-label="第 ${i + 1} 段，${c.short}" aria-pressed="${i === 0}"><span>${String(i + 1).padStart(2, "0")}</span>${c.short}</button>`).join("")}</div><div class="story-progress" role="progressbar" aria-label="星光高鐵故事進度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i></i></div></div>
    <div class="story-discovery-note" id="story-discovery-note" role="status">三個小驚喜，隨時都能點開。</div>
    <div class="story-letter" id="story-letter" hidden><span aria-hidden="true">✉ ✦</span><h2>給小小站長的一封信</h2><p>謝謝你陪我旅行！我們一起接好軌道、分享點心，再去山海風景找寶物吧。</p><div><button data-story-game="tracks">⌁ 幫列車接軌道</button><button data-story-game="sharing">🍎 和朋友分點心</button><button data-story-game="treasure">✦ 去山海尋寶</button></div><button id="story-letter-close" class="story-letter-close">收好信，繼續看風景</button></div>
    <span class="story-credit">AI 電影風素材 · 星光高鐵為想像故事列車</span>
  </section>`;
}
export function mountStory(
  root,
  { state, reduced, onRead, onSound, onGame, onAnnounce },
) {
  let frame = null,
    lastTime = null,
    visible = true,
    stopped = false,
    activeChapter = -1,
    lastPercent = -1;
  let size = { width: root.clientWidth, height: root.clientHeight };
  const train = root.querySelector("#story-train"),
    progress = root.querySelector('[role="progressbar"]'),
    caption = root.querySelector("#story-caption"),
    toggle = root.querySelector("#story-toggle"),
    note = root.querySelector("#story-motion-note"),
    letter = root.querySelector("#story-letter");
  function update() {
    const p = storyProgress(state),
      chapter = storyChapter(state),
      c = CHAPTERS[chapter];
    train.style.setProperty("--travel", String(p));
    // Keep the composited vehicle on the pictured rail after cover-cropping at any width.
    const mobile = size.width <= 760,
      spriteWidth = mobile ? 230 : size.width <= 1000 ? 290 : 320;
    const vehicleScale = mobile ? 0.75 + p * 0.25 : 0.77 + p * 0.23;
    const noseY =
      ((mobile ? 55 + p * 410 : -210 + p * 570) +
        spriteWidth * 1.5 * (1 - 0.075 * vehicleScale)) /
      size.height;
    const imageWidth = 1672 * Math.max(size.width / 1672, size.height / 941);
    const railX =
      (0.6 + 0.028 * Math.max(0, Math.min(1, noseY))) * imageWidth -
      (imageWidth - size.width) * (mobile ? 0.58 : 0.61);
    train.style.setProperty("--rail-x", `${railX}px`);
    const percent = Math.round(p * 100);
    if (lastPercent !== percent) {
      progress.setAttribute("aria-valuenow", String(percent));
      progress.querySelector("i").style.width = `${percent}%`;
      lastPercent = percent;
    }
    if (activeChapter !== chapter) {
      caption.querySelector("h2").textContent = c.title;
      caption.querySelector("p").textContent = c.text;
      root.querySelector("#story-place").textContent = c.place;
      root
        .querySelectorAll("[data-chapter]")
        .forEach((b) =>
          b.setAttribute(
            "aria-pressed",
            String(Number(b.dataset.chapter) === chapter),
          ),
        );
      activeChapter = chapter;
    }
    root.classList.toggle("story-arrived", p === 1);
    root.classList.toggle(
      "story-moving",
      state.playing && !reduced && visible && !document.hidden,
    );
    root.classList.toggle("story-still", reduced);
    const toggleText =
      p === 1
        ? "↺ 再看一次"
        : state.playing && !reduced
          ? "Ⅱ 暫停故事"
          : "▶ 播放故事";
    if (toggle.textContent !== toggleText) toggle.textContent = toggleText;
    toggle.disabled = reduced && p < 1;
    root.querySelector("#story-next").disabled = p === 1;
    const motionText = reduced
      ? "已減少動畫；可按「下一段」或下方故事段落閱讀。"
      : "36 秒的山海旅程，隨時可以暫停。";
    if (note.textContent !== motionText) note.textContent = motionText;
    letter.hidden = !state.letterOpen;
    root.querySelectorAll("[data-discover]").forEach((b) => {
      const pressed = String(state.discoveries.includes(b.dataset.discover));
      if (b.getAttribute("aria-pressed") !== pressed)
        b.setAttribute("aria-pressed", pressed);
    });
  }
  function cancel() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    lastTime = null;
  }
  function schedule() {
    if (
      !stopped &&
      state.playing &&
      !reduced &&
      visible &&
      !document.hidden &&
      frame === null
    )
      frame = requestAnimationFrame(tick);
  }
  function tick(now) {
    frame = null;
    if (stopped || reduced || !visible || document.hidden || !state.playing) {
      lastTime = null;
      return;
    }
    if (lastTime !== null)
      Object.assign(state, advanceStory(state, Math.max(0, now - lastTime)));
    lastTime = now;
    update();
    schedule();
  }
  const discoveries = {
    bird: "啾啾！小鳥說：先看看兩段軌道有沒有接在一起。",
    light: "燈塔亮了！海邊小站準備迎接星光高鐵。",
    letter: "星光信封裡，藏著三個可以馬上玩的新任務。",
  };
  function handleClick(event) {
    const b = event.target.closest("button");
    if (!b || !root.contains(b)) return;
    if (b.dataset.chapter !== undefined) {
      Object.assign(state, goToChapter(state, Number(b.dataset.chapter)));
      cancel();
      update();
      onAnnounce(CHAPTERS[storyChapter(state)].title);
      return;
    }
    if (b.dataset.discover) {
      const key = b.dataset.discover;
      if (!state.discoveries.includes(key)) state.discoveries.push(key);
      root.querySelector("#story-discovery-note").textContent =
        discoveries[key];
      if (key === "letter") {
        state.letterOpen = true;
        state.playing = false;
        cancel();
      }
      onSound();
      update();
      onAnnounce(discoveries[key]);
      if (key === "letter") root.querySelector("[data-story-game]")?.focus();
      return;
    }
    if (b.dataset.storyGame) {
      onGame(b.dataset.storyGame);
      return;
    }
    if (b.id === "story-letter-close") {
      state.letterOpen = false;
      update();
      root.querySelector("[data-discover='letter']")?.focus();
      return;
    }
    if (b.id === "story-read") {
      state.playing = false;
      cancel();
      update();
      onRead(CHAPTERS[storyChapter(state)].text);
      return;
    }
    if (b.id === "story-next") {
      Object.assign(
        state,
        goToChapter(state, Math.min(3, storyChapter(state) + 1)),
      );
      cancel();
      update();
      onAnnounce(CHAPTERS[storyChapter(state)].title);
      return;
    }
    if (
      b.id === "story-replay" ||
      (b.id === "story-toggle" && state.elapsed === STORY_DURATION)
    ) {
      Object.assign(state, { elapsed: 0, playing: true, letterOpen: false });
      cancel();
      update();
      schedule();
      return;
    }
    if (b.id === "story-toggle" && !reduced) {
      state.playing = !state.playing;
      cancel();
      update();
      schedule();
    }
  }
  function visibility() {
    cancel();
    update();
    schedule();
  }
  const observer = new IntersectionObserver(
    ([entry]) => {
      visible = entry.isIntersecting;
      cancel();
      update();
      schedule();
    },
    { threshold: 0.05 },
  );
  const resizeObserver = new ResizeObserver(() => {
    size = { width: root.clientWidth, height: root.clientHeight };
    update();
  });
  resizeObserver.observe(root);
  observer.observe(root);
  root.addEventListener("click", handleClick);
  document.addEventListener("visibilitychange", visibility);
  update();
  schedule();
  return {
    pause() {
      state.playing = false;
      cancel();
      update();
    },
    setReduced(value) {
      reduced = value;
      cancel();
      update();
      schedule();
    },
    destroy() {
      stopped = true;
      cancel();
      observer.disconnect();
      resizeObserver.disconnect();
      root.removeEventListener("click", handleClick);
      document.removeEventListener("visibilitychange", visibility);
    },
  };
}
