export const DIRECTIONS = ["上", "右", "下", "左"];
export const SOUVENIRS = [
  {
    id: "star-letter",
    icon: "✉",
    name: "星光信封",
    story: "把今天的新發現，寄給明天的自己。",
  },
  {
    id: "lighthouse",
    icon: "🗼",
    name: "海邊燈塔",
    story: "小小一道光，陪列車找到海邊小站。",
  },
  {
    id: "forest-leaf",
    icon: "🍃",
    name: "森林葉子",
    story: "葉子說：慢慢走，也會發現漂亮的風景。",
  },
  {
    id: "cloud",
    icon: "☁",
    name: "山谷雲朵",
    story: "軟軟的雲，像一張舒服的列車小枕頭。",
  },
  {
    id: "ticket",
    icon: "🎟",
    name: "冒險車票",
    story: "這張車票，記得你完成的一趟旅行。",
  },
  {
    id: "apple",
    icon: "🍎",
    name: "分享蘋果",
    story: "和朋友分享，開心也變成兩份。",
  },
  {
    id: "mountain",
    icon: "⛰",
    name: "青山徽章",
    story: "小小工程師，謝謝你讓列車順利出發。",
  },
  {
    id: "bird",
    icon: "🐦",
    name: "唱歌小鳥",
    story: "啾啾！今天你又認識一台漂亮列車。",
  },
  {
    id: "clock",
    icon: "◷",
    name: "車站小鐘",
    story: "不用趕時間，想一想也沒關係。",
  },
  {
    id: "rainbow",
    icon: "🌈",
    name: "雨後彩虹",
    story: "每一次再試，都可能帶來新的發現。",
  },
  {
    id: "shell",
    icon: "🐚",
    name: "海浪貝殼",
    story: "把耳朵靠近，好像聽見下一站的海浪。",
  },
  {
    id: "spark",
    icon: "✦",
    name: "小站星星",
    story: "每位小站長，都有自己閃亮的地方。",
  },
];
export function pickSouvenir(progress, trainId) {
  const remaining = SOUVENIRS.filter(
    (item) => !progress.souvenirs.includes(item.id),
  );
  const pool = remaining.length ? remaining : SOUVENIRS;
  const hash = [...trainId].reduce(
    (n, char) => n + char.charCodeAt(0),
    progress.trips * 17,
  );
  return pool[hash % pool.length];
}
export function railLinks(kind, rotation) {
  if (kind === "empty") return [];
  return (kind === "straight" ? [0, 2] : [0, 1]).map((d) => (d + rotation) % 4);
}
export function trackConnected(q, rotations) {
  if (
    !Array.isArray(rotations) ||
    rotations.length !== q.tiles.length ||
    rotations.some((v) => !Number.isInteger(v) || v < 0 || v > 3)
  )
    return false;
  let cell = q.start,
    incoming = 3;
  const visited = new Set();
  while (!visited.has(cell)) {
    visited.add(cell);
    const links = railLinks(q.tiles[cell].kind, rotations[cell]);
    if (links.length !== 2 || !links.includes(incoming)) return false;
    const outgoing = links.find((d) => d !== incoming);
    const x = cell % q.columns,
      y = Math.floor(cell / q.columns);
    const nx = x + [0, 1, 0, -1][outgoing],
      ny = y + [-1, 0, 1, 0][outgoing];
    if (nx < 0 || nx >= q.columns || ny < 0 || ny >= q.rows)
      return cell === q.finish && outgoing === 1;
    cell = ny * q.columns + nx;
    incoming = (outgoing + 2) % 4;
  }
  return false;
}
export function newAdventureState(q) {
  return {
    rotations: q.tiles?.map((tile) => tile.initial) || [],
    shares: Array(q.friends || 0).fill(0),
    found: new Set(),
    trackHint: false,
    treasureHint: false,
  };
}
export function changeShare(q, shares, index, delta) {
  if (
    !Number.isInteger(index) ||
    index < 0 ||
    index >= q.friends ||
    ![-1, 1].includes(delta) ||
    shares.length !== q.friends
  )
    return shares;
  if (delta === 1 && shares.reduce((a, b) => a + b, 0) >= q.total)
    return shares;
  if (delta === -1 && shares[index] === 0) return shares;
  return shares.map((n, i) => n + (i === index ? delta : 0));
}
export function createAdventureQuestion({
  game,
  level,
  max,
  rng,
  randomInt,
  shuffle,
}) {
  if (game === "tracks") {
    const columns = level === "small" ? 2 : 3,
      rows = columns;
    const path =
      level === "small"
        ? [0, 1, 3]
        : level === "medium"
          ? [0, 1, 4, 7, 8]
          : rng() < 0.5
            ? [0, 3, 4, 1, 2, 5, 8]
            : [0, 1, 4, 3, 6, 7, 8];
    const direction = (from, to) =>
      to === from - columns
        ? 0
        : to === from + 1
          ? 1
          : to === from + columns
            ? 2
            : 3;
    const tiles = Array.from({ length: columns * rows }, (_, index) => {
      const at = path.indexOf(index);
      if (at === -1) return { kind: "empty", initial: 0, solution: 0 };
      const inDir = at === 0 ? 3 : direction(index, path[at - 1]),
        outDir = at === path.length - 1 ? 1 : direction(index, path[at + 1]);
      const kind = (inDir + 2) % 4 === outDir ? "straight" : "curve";
      const solution = [0, 1, 2, 3].find(
        (r) =>
          railLinks(kind, r).includes(inDir) &&
          railLinks(kind, r).includes(outDir),
      );
      return { kind, solution, initial: randomInt(0, 3, rng) };
    });
    const q = {
      game,
      level,
      columns,
      rows,
      path,
      tiles,
      start: path[0],
      finish: path.at(-1),
      answer: "connected",
      prompt: "轉轉軌道，把列車接到小站。",
      hint: "從起點跟著軌道走。兩格交界的鐵軌要接在一起；亮起的線是參考路線。",
    };
    if (
      trackConnected(
        q,
        tiles.map((t) => t.initial),
      )
    )
      tiles[q.start].initial = (tiles[q.start].initial + 1) % 4;
    return q;
  }
  if (game === "sharing") {
    const friends = level === "small" ? 2 : randomInt(2, 3, rng);
    const each = randomInt(1, Math.floor(max / friends), rng);
    const food = ["🍎", "🍓", "🍊"][randomInt(0, 2, rng)];
    return {
      game,
      level,
      friends,
      total: friends * each,
      food,
      answer: Array(friends).fill(each),
      prompt: `把 ${friends * each} 份點心，分給 ${friends} 位朋友，讓每位一樣多。`,
      hint: "一次給每位朋友一份，再分下一輪。多了可以搬回點心籃。",
    };
  }
  if (game === "treasure") {
    const target = randomInt(
        2,
        level === "small" ? 3 : level === "medium" ? 4 : 5,
        rng,
      ),
      size = level === "small" ? 9 : 12;
    const icons = shuffle(["star", "leaf", "shell"], rng),
      kind = icons[0];
    const items = shuffle(
      [
        ...Array(target).fill(kind),
        ...Array.from({ length: size - target }, (_, i) => icons[1 + (i % 2)]),
      ],
      rng,
    );
    const names = { star: "星星", leaf: "葉子", shell: "貝殼" };
    return {
      game,
      level,
      items,
      target: kind,
      answer: target,
      prompt: `山海風景裡，找出 ${target} 個${names[kind]}。`,
      hint: `只找${names[kind]}，每個點一次。找到的會亮起來；其他小東西可以下次再看。`,
    };
  }
  throw new Error("Unknown adventure");
}
