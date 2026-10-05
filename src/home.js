import { LEVELS, GAMES, allowedGames } from "./engine.js?v=1.8.1";
import { storyMarkup } from "./story.js?v=1.8.1";

export const DESTINATIONS = [
  {
    game: "pattern",
    place: "海風小站",
    marker: "01",
    hint: "接上一節，發現規律",
    className: "coast",
  },
  {
    game: "cargo",
    place: "森林貨運站",
    marker: "02",
    hint: "裝好貨物，準備送達",
    className: "depot",
  },
  {
    game: "memory",
    place: "列車車庫",
    marker: "03",
    hint: "翻開列車，找好朋友",
    className: "roundhouse",
  },
  {
    game: "clock",
    place: "鐘樓車站",
    marker: "04",
    hint: "認識時鐘，準時出發",
    className: "tower",
  },
];

export function homeMarkup({
  trains,
  selected,
  progress,
  practice,
  mood,
  esc,
  image,
  levelButtons,
}) {
  const t = trains.find((train) => train.id === selected) || trains[0];
  const games = allowedGames(progress.level);
  const puzzlePieces = { small: 4, medium: 6, large: 9 }[progress.level];
  const destination = DESTINATIONS.find((d) => d.game === practice);
  const featured = [
    ...new Set([
      selected,
      "700t",
      "e5",
      "l0",
      "emu3000",
      "forest-dl25-30",
      "temu2000",
    ]),
  ]
    .map((id) => trains.find((train) => train.id === id))
    .filter(Boolean)
    .slice(0, 6);
  return `${storyMarkup()}
    <section id="railway-map" class="railway-world ${mood === "blue" ? "blue-hour" : ""}" aria-labelledby="world-title">
      <img class="world-image" src="assets/images/railway-world-v2.webp" alt="想像的台灣山海鐵道樂園，包含鐘樓車站、森林貨運站、扇形車庫及海邊月台" width="1672" height="941" loading="lazy" decoding="async">
      <div class="world-shade"></div>
      <div class="world-copy"><div class="eyebrow"><span></span> 給 3–8 歲的小小鐵道迷</div><h2 id="world-title">今天，<br>想去哪裡<span>冒險？</span></h2><p>點亮一座小站，<br>讓喜歡的列車帶你發現數學。</p><a href="#departure" class="primary-btn">準備上車 <span aria-hidden="true">→</span></a><span class="world-kind">自由探索 · 沒有倒數 · 答錯再試</span></div>
      <div class="world-controls" role="group" aria-label="場景氣氛"><button data-mood="golden" aria-pressed="${mood === "golden"}">☀ 暖陽</button><button data-mood="blue" aria-pressed="${mood === "blue"}">☾ 暮色</button><button id="station-bell" aria-label="聽進站鈴聲" ${progress.effects ? "" : "disabled"}>♪ 進站鈴</button></div>
      <div class="map-pins" role="group" aria-label="探索四座任務車站">${DESTINATIONS.map(
        (d) => {
          const available = games.includes(d.game);
          return `<button class="map-pin ${d.className} ${practice === d.game ? "active" : ""}" data-destination="${d.game}" aria-pressed="${practice === d.game}"><span class="pin-symbol" aria-hidden="true">${GAMES[d.game].icon}</span><span><strong>${d.place}</strong><small>${available ? GAMES[d.game].name : "5 歲以上 · 認識時鐘"}</small></span><i aria-hidden="true">${d.marker}</i></button>`;
        },
      ).join("")}</div>
      <div class="world-preview" role="status"><span class="preview-icon" aria-hidden="true">${destination ? GAMES[practice].icon : "✦"}</span><div><small>${destination ? `目的地 · ${destination.place}` : "探索地圖，或選一趟驚喜旅程"}</small><strong>${destination ? destination.hint : "每次出發，都有新的發現"}</strong></div><button id="map-depart" class="world-depart">${destination ? "搭車去這裡" : "驚喜出發"} →</button></div>
      <span class="world-credit">AI 電影風想像場景 · 非實際路線圖</span>
    </section>
    <div class="content-wrap home-content">
      <section class="new-adventures" aria-labelledby="adventure-title"><div><div class="eyebrow dark">PLAY THE STORY</div><h2 id="adventure-title">把故事，變成你的小冒險</h2><p>接好路、分點心、找寶物。點一下就能開始。</p></div><div class="adventure-launchers">${["tracks", "sharing", "treasure"].map((id) => `<button data-mission="${id}" aria-label="${GAMES[id].name}，開始故事任務"><span aria-hidden="true">${GAMES[id].icon}</span><strong>${GAMES[id].name}</strong><small>${GAMES[id].description}</small><b>出發 →</b></button>`).join("")}</div></section>
      <section class="departure" id="departure"><div class="section-heading"><div><div class="eyebrow dark">YOUR NEXT ADVENTURE</div><h2>小站長，準備出發！</h2></div><p>先選適合的難度，每趟 ${LEVELS[progress.level].stops} 個任務。</p></div><div class="levels">${levelButtons()}</div><p class="age-note" id="age-note" role="status">年齡是參考，可以按孩子的理解程度選難度。</p>
        <div class="boarding-pass"><div class="pass-image">${image(t)}</div><div class="pass-info"><small>今天陪你的列車</small><strong id="selected-name">${esc(t.cardLabel)}</strong><button class="text-btn" data-detail="${t.id}">認識這台列車 ↗</button></div><label class="practice-picker"><span>今天想玩</span><select id="practice-select"><option value="mixed" ${practice === "mixed" ? "selected" : ""}>驚喜旅程 · 任務隨機搭配</option>${games.map((id) => `<option value="${id}" ${practice === id ? "selected" : ""}>${GAMES[id].name}</option>`).join("")}</select></label><button class="primary-btn" id="trip-start">上車，出發！ →</button></div>
      </section>
      <section class="playroom" id="playroom" aria-labelledby="playroom-title">
        <div class="section-heading"><div><div class="eyebrow dark">小站長的遊戲室</div><h2 id="playroom-title">拼一拼、分一分，自己找條路</h2></div><p>三種新玩法，換個方式探索火車世界。</p></div>
        <div class="playroom-games">
          <button class="playroom-card puzzle-launch" data-mission="puzzle" aria-label="火車拼圖，開始 ${puzzlePieces} 片拼圖旅程"><div class="playroom-photo">${image(t)}<div class="photo-grid" aria-hidden="true" style="--preview-cols:${progress.level === "small" ? 2 : 3};--preview-rows:${progress.level === "large" ? 3 : 2}">${Array.from({ length: puzzlePieces }, () => "<i></i>").join("")}</div><span>${puzzlePieces} 片</span></div><div class="playroom-card-copy"><strong>火車拼圖</strong><p>找出相接的線條，把列車與風景拼回來。</p><b>開始拼圖 →</b></div></button>
          <button class="playroom-card luggage-launch" data-mission="luggage" aria-label="行李分類站，開始旅程"><div class="playroom-symbol" aria-hidden="true"><span class="mini-case case-one">●</span><span class="mini-case case-two">▲</span><span class="mini-case case-three">■</span></div><div class="playroom-card-copy"><strong>行李分類站</strong><p>看顏色、看形狀，幫行李找到合適的籃子。</p><b>整理行李 →</b></div></button>
          <button class="playroom-card maze-launch" data-mission="maze" aria-label="車站迷宮，開始旅程"><div class="playroom-symbol" aria-hidden="true"><span class="mini-maze">🚆 <i>┐<br>└─┐<br>　🏠</i></span></div><div class="playroom-card-copy"><strong>車站迷宮</strong><p>轉彎、探路，帶小火車走到終點站。</p><b>找路出發 →</b></div></button>
        </div>
        <a class="playroom-gifts text-link" href="#stamps">打開六個主題的收藏冊，玩玩你的小禮物 →</a>
      </section>
      <section class="home-trains" aria-labelledby="home-trains-title"><div class="section-heading"><div><div class="eyebrow dark">CHOOSE YOUR TRAIN</div><h2 id="home-trains-title">挑一台喜歡的火車</h2></div><a class="text-link" href="#collection">探索 ${trains.length} 款列車與名稱 →</a></div><div class="featured-trains">${featured.map((train) => `<button class="featured-train ${train.id === selected ? "chosen" : ""}" data-select="${train.id}" aria-label="選擇${esc(train.cardLabel)}" aria-pressed="${train.id === selected}">${image(train)}<span><strong>${esc(train.name)}</strong><small>${esc(train.model)}${train.status === "experimental" ? " · 試驗列車" : ""}</small></span><i aria-hidden="true">${train.id === selected ? "✓" : "+"}</i></button>`).join("")}</div></section>
      <section class="mission-hall" id="missions" aria-labelledby="mission-title"><div class="section-heading"><div><div class="eyebrow dark">${Object.keys(GAMES).length} WAYS TO DISCOVER</div><h2 id="mission-title">今天想玩哪一種？</h2></div><p>點選任務，搭喜歡的列車直接出發。</p></div><div class="mission-grid">${Object.entries(
        GAMES,
      )
        .map(([id, g], i) => {
          const available = games.includes(id);
          return `<button class="mission-card ${practice === id ? "active" : ""} ${available ? "" : "later"}" data-mission="${id}" aria-pressed="${practice === id}" aria-label="${g.name}${available ? "，開始旅程" : "，適合 5–8 歲，查看提示"}"><span class="mission-number">${String(i + 1).padStart(2, "0")}</span><span class="mission-symbol" aria-hidden="true">${g.icon}</span><strong>${g.name}</strong><p>${g.description}</p><small>${available ? (practice === id ? "搭這台列車出發 →" : "立即出發 →") : "適合 5–8 歲"}</small></button>`;
        })
        .join(
          "",
        )}</div><p class="home-notice" id="home-notice" role="status">孩子可以慢慢想。完成任務就能集章，使用提示也一樣。</p></section>
      <section class="passport-invite"><span aria-hidden="true">✦</span><div><h2>每趟旅程，留下一個回憶</h2><p>你已經完成 ${progress.trips} 趟旅程。下一枚列車紀念章正在等你。</p></div><a href="#stamps" class="secondary-btn">打開我的鐵道護照 →</a></section>
    </div>`;
}
