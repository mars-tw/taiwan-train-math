import { createAdventureQuestion, SOUVENIRS } from "./adventure.js?v=1.2.0";
export const LEVELS = {
  small: {
    name: "小小站長",
    age: "3–4 歲",
    label: "數數與配對",
    max: 5,
    stops: 3,
  },
  medium: {
    name: "火車助手",
    age: "5–6 歲",
    label: "10 以內加減",
    max: 10,
    stops: 5,
  },
  large: {
    name: "小小列車長",
    age: "7–8 歲",
    label: "20 以內加減",
    max: 20,
    stops: 5,
  },
};
export const GAMES = {
  count: {
    name: "數數看",
    icon: "●",
    description: "點點乘客，數一數有幾位。",
    levels: ["small", "medium", "large"],
  },
  identify: {
    name: "找火車",
    icon: "🚆",
    description: "看列車、聽名字，找到好朋友。",
    levels: ["small", "medium", "large"],
  },
  boarding: {
    name: "上車下車",
    icon: "＋",
    description: "看乘客移動，一起練習加減。",
    levels: ["medium", "large"],
  },
  order: {
    name: "排車廂",
    icon: "123",
    description: "點選數字，把車廂從小到大排好。",
    levels: ["small", "medium", "large"],
  },
  compare: {
    name: "比一比",
    icon: "⇄",
    description: "把車票配對，找出哪邊比較多。",
    levels: ["medium", "large"],
  },
  pattern: {
    name: "規律小火車",
    icon: "◆",
    description: "看看車廂的規律，接上下一節。",
    levels: ["small", "medium", "large"],
  },
  cargo: {
    name: "貨物裝箱",
    icon: "▣",
    description: "親手放入貨物，裝到剛剛好的數量。",
    levels: ["small", "medium", "large"],
  },
  memory: {
    name: "列車記憶翻卡",
    icon: "▧",
    description: "翻開兩張卡，找出一樣的列車。",
    levels: ["small", "medium", "large"],
  },
  clock: {
    name: "車站時鐘",
    icon: "◷",
    description: "看時針和分針，找到出發時間。",
    levels: ["medium", "large"],
  },
  tracks: {
    name: "路線小工程師",
    icon: "⌁",
    description: "轉轉軌道，接通列車到小站的路。",
    levels: ["small", "medium", "large"],
  },
  sharing: {
    name: "列車點心派對",
    icon: "🍎",
    description: "親手分點心，讓朋友們一樣多。",
    levels: ["small", "medium", "large"],
  },
  treasure: {
    name: "山海尋寶",
    icon: "✦",
    description: "探索風景，找到藏起來的小寶物。",
    levels: ["small", "medium", "large"],
  },
};
export const allowedGames = (level) =>
  Object.keys(GAMES).filter((id) => GAMES[id].levels.includes(level));
export const SHAPES = {
  circle: { symbol: "●", name: "圓形" },
  diamond: { symbol: "◆", name: "菱形" },
  square: { symbol: "■", name: "正方形" },
  triangle: { symbol: "▲", name: "三角形" },
};
export function clockLabel(value) {
  const hour = Math.floor(value / 60);
  return `${hour} 點${value % 60 ? "半" : "整"}`;
}
export function newMemoryState() {
  return { open: [], matched: [], turns: 0 };
}
export function memoryTurn(state, index, deck) {
  if (
    !Number.isInteger(index) ||
    index < 0 ||
    index >= deck.length ||
    state.open.length === 2 ||
    state.open.includes(index) ||
    state.matched.includes(index)
  )
    return state;
  const open = [...state.open, index];
  if (open.length === 2 && deck[open[0]] === deck[open[1]])
    return {
      open: [],
      matched: [...state.matched, ...open],
      turns: state.turns + 1,
    };
  return { ...state, open, turns: state.turns + (open.length === 2 ? 1 : 0) };
}
export function seededRandom(seed) {
  let n = seed >>> 0;
  return () => {
    n = (Math.imul(n, 1664525) + 1013904223) >>> 0;
    return n / 4294967296;
  };
}
export function shuffle(values, rng = Math.random) {
  const a = [...values];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
export function randomInt(min, max, rng = Math.random) {
  return min + Math.floor(rng() * (max - min + 1));
}
function options(answer, max, count, rng) {
  const pool = shuffle(
    Array.from({ length: max + 1 }, (_, i) => i).filter((n) => n !== answer),
    rng,
  );
  return shuffle([answer, ...pool.slice(0, count - 1)], rng);
}
export function questionFor({
  level,
  game,
  train,
  trains,
  rng = Math.random,
  challenge = false,
}) {
  const cfg = LEVELS[level];
  if (!cfg) throw new Error("Unknown level");
  if (!allowedGames(level).includes(game))
    throw new Error("Game not available for this level");
  if (["tracks", "sharing", "treasure"].includes(game))
    return createAdventureQuestion({
      game,
      level,
      max: cfg.max,
      rng,
      randomInt,
      shuffle,
    });
  if (game === "pattern") {
    if (level === "large") {
      const step = randomInt(2, 3, rng),
        start = randomInt(0, cfg.max - step * 4, rng);
      const sequence = Array.from({ length: 4 }, (_, i) =>
        String(start + i * step),
      );
      const answer = String(start + step * 4);
      return {
        game,
        level,
        kind: "number",
        sequence,
        step,
        answer,
        choices: options(Number(answer), cfg.max, 3, rng).map(String),
        prompt: "每次多一樣多，下一節車廂是幾號？",
        hint: `每次加 ${step}。${sequence.at(-1)} 再加 ${step}，就是 ${answer}。`,
      };
    }
    const shapes = shuffle(Object.keys(SHAPES), rng);
    const unit =
      level === "small"
        ? shapes.slice(0, 2)
        : rng() < 0.5
          ? [shapes[0], shapes[0], shapes[1]]
          : shapes.slice(0, 3);
    const sequence = Array.from(
      { length: unit.length * 2 },
      (_, i) => unit[i % unit.length],
    );
    return {
      game,
      level,
      kind: "shape",
      sequence,
      unit,
      answer: unit[0],
      choices: shuffle(shapes.slice(0, level === "small" ? 2 : 3), rng),
      prompt: "看看重複的規律，下一節車廂放什麼？",
      hint: `一組是${unit.map((s) => SHAPES[s].name).join("、")}。再從${SHAPES[unit[0]].name}開始。`,
    };
  }
  if (game === "cargo") {
    const answer = randomInt(1, cfg.max, rng);
    return {
      game,
      level,
      answer,
      max: cfg.max,
      prompt: `請幫貨運列車裝 ${answer} 箱貨物。`,
      hint: `每箱算一個。目標是 ${answer} 箱，多了可以點貨物搬回來。`,
    };
  }
  if (game === "memory") {
    const count = { small: 2, medium: 3, large: 4 }[level];
    const pool = [
      train,
      ...shuffle(
        trains.filter((t) => t.id !== train.id && t.status !== "future"),
        rng,
      ),
    ];
    const unique = pool
      .filter(
        (t, i) =>
          pool.findIndex(
            (other) => other.image === t.image || other.name === t.name,
          ) === i,
      )
      .slice(0, count);
    const pairs = unique.map((t) => t.id);
    return {
      game,
      level,
      pairs,
      deck: shuffle([...pairs, ...pairs], rng),
      answer: pairs.length,
      prompt: "翻開兩張卡，找出一樣的列車。",
      hint: "一起看看列車長什麼樣子。記住位置，再試著翻出一對。",
    };
  }
  if (game === "clock") {
    const hour = randomInt(1, 12, rng),
      minute = level === "large" && rng() < 0.5 ? 30 : 0;
    const answer = hour * 60 + minute;
    const pool = Array.from(
      { length: level === "large" ? 24 : 12 },
      (_, i) =>
        (Math.floor(i / (level === "large" ? 2 : 1)) + 1) * 60 +
        (level === "large" ? (i % 2) * 30 : 0),
    );
    return {
      game,
      level,
      hour,
      minute,
      answer,
      choices: shuffle(
        [
          answer,
          ...shuffle(
            pool.filter((n) => n !== answer),
            rng,
          ).slice(0, 2),
        ],
        rng,
      ),
      prompt: "車站時鐘指向幾點？找到列車出發時間。",
      hint: minute
        ? `長長的分針指向 6，是半點。短短的時針在 ${hour} 和 ${hour === 12 ? 1 : hour + 1} 中間，是 ${hour} 點半。`
        : `長長的分針指向 12，是整點。短短的時針指向 ${hour}，是 ${hour} 點整。`,
    };
  }
  if (game === "identify") {
    const candidates = trains.filter(
      (t) =>
        t.id !== train.id &&
        t.name !== train.name &&
        t.model !== train.model &&
        t.image !== train.image &&
        t.status !== "future",
    );
    const choices = shuffle(
      [
        train.id,
        ...shuffle(candidates, rng)
          .slice(0, level === "small" ? 1 : 2)
          .map((t) => t.id),
      ],
      rng,
    );
    return {
      game,
      level,
      target: train.id,
      prompt:
        level === "large" && train.modelKind === "type"
          ? `請找到型號是 ${train.model} 的列車。`
          : `請找到${train.name}。`,
      answer: train.id,
      choices,
      hint: `一起看列車卡。這是${train.name}，${train.modelKind === "type" ? `型號是 ${train.model}。` : "這是一個列車名稱。"}`,
    };
  }
  if (game === "count") {
    const count = randomInt(level === "small" ? 1 : 0, cfg.max, rng);
    return {
      game,
      level,
      count,
      answer: count,
      choices: options(count, cfg.max, level === "small" ? 2 : 3, rng),
      prompt:
        level === "small"
          ? "月台有幾位乘客？選一樣多的點點。"
          : "月台有幾位乘客？",
      hint:
        count === 0
          ? "月台還沒有乘客，所以是零人。"
          : `每位乘客點一次，一起數到 ${count}。`,
    };
  }
  if (game === "compare") {
    const left = randomInt(1, Math.min(cfg.max, 10), rng),
      right = randomInt(1, Math.min(cfg.max, 10), rng);
    return {
      game,
      level,
      left,
      right,
      answer: left === right ? "equal" : left > right ? "left" : "right",
      choices: ["left", "equal", "right"],
      prompt: "哪一邊的車票比較多？",
      hint: `左邊 ${left} 張，右邊 ${right} 張。可以把車票一張一張配對。`,
    };
  }
  if (game === "boarding") {
    if (level === "small") throw new Error("No arithmetic in small level");
    const operation = rng() < 0.5 ? "add" : "subtract";
    const start = randomInt(1, cfg.max, rng);
    const cap = operation === "subtract" ? start : cfg.max - start;
    const boundary =
      level === "large" && !challenge
        ? Math.min(cap, operation === "add" ? 10 - (start % 10) : start % 10)
        : cap;
    const change = randomInt(0, Math.max(0, boundary), rng);
    const answer = operation === "add" ? start + change : start - change;
    return {
      game,
      level,
      start,
      change,
      operation,
      answer,
      choices: options(answer, cfg.max, 3, rng),
      prompt:
        operation === "add"
          ? `車上有 ${start} 人，又上來 ${change} 人，現在有幾人？`
          : `車上有 ${start} 人，下車 ${change} 人，還有幾人？`,
      hint: `${start} ${operation === "add" ? "加" : "減"} ${change} 是 ${answer}。看留下來的乘客，一起數數看。`,
    };
  }
  if (game === "order") {
    const length = level === "small" ? 3 : 5;
    const start =
      level === "large" ? randomInt(0, cfg.max - length + 1, rng) : 1;
    const answer = Array.from({ length }, (_, i) => start + i);
    let numbers = shuffle(answer, rng);
    if (numbers.every((n, i) => n === answer[i])) numbers.reverse();
    return {
      game,
      level,
      numbers,
      answer,
      prompt: "請把車廂從小到大排好。",
      hint: `先找到最小的 ${start}，再找下一個數字。`,
    };
  }
  throw new Error("Unknown game");
}
export function createTrip({
  level,
  train,
  trains,
  rng = Math.random,
  challenge = false,
  practice = "mixed",
}) {
  if (!LEVELS[level]) throw new Error("Unknown level");
  const pool = allowedGames(level).filter(
    (game) => !["count", "identify"].includes(game),
  );
  const sequence =
    practice === "mixed"
      ? [
          "count",
          ...shuffle(pool, rng).slice(0, LEVELS[level].stops - 2),
          "identify",
        ]
      : Array(LEVELS[level].stops).fill(practice);
  return sequence.map((game) =>
    questionFor({ level, game, train, trains, rng, challenge }),
  );
}
export function isCorrect(q, answer) {
  return Array.isArray(q.answer)
    ? Array.isArray(answer) &&
        q.answer.length === answer.length &&
        q.answer.every((v, i) => v === answer[i])
    : q.answer === answer;
}
export const STORAGE_KEY = "taiwan-train-math.v1";
export const defaults = () => ({
  version: 1,
  level: "small",
  voice: false,
  effects: true,
  reduceMotion: false,
  challenge: false,
  completed: [],
  souvenirs: [],
  trips: 0,
});
export function readProgress(storage) {
  try {
    const raw = JSON.parse(storage.getItem(STORAGE_KEY));
    if (!raw || raw.version !== 1) return defaults();
    const result = defaults();
    for (const key of ["voice", "effects", "reduceMotion", "challenge"])
      if (typeof raw[key] === "boolean") result[key] = raw[key];
    if (LEVELS[raw.level]) result.level = raw.level;
    result.completed = Array.isArray(raw.completed)
      ? [...new Set(raw.completed.filter((id) => typeof id === "string"))]
      : [];
    result.souvenirs = Array.isArray(raw.souvenirs)
      ? [
          ...new Set(
            raw.souvenirs.filter((id) =>
              SOUVENIRS.some((item) => item.id === id),
            ),
          ),
        ]
      : [];
    result.trips =
      Number.isSafeInteger(raw.trips) && raw.trips >= 0 ? raw.trips : 0;
    return result;
  } catch {
    return defaults();
  }
}
export function saveProgress(storage, value) {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}
