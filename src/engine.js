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
  const small = ["count", "identify", "order"];
  const other = ["count", "boarding", "identify", "order", "compare"];
  const sequence =
    practice === "mixed"
      ? level === "small"
        ? small
        : other
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
