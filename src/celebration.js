// Small, offline feedback helpers: synthesized sound cues and decorative bursts.
// Nothing here loads a file or contacts a network service.

const freeze = cue => Object.freeze({ ...cue, notes: Object.freeze(cue.notes.map(note => Object.freeze([...note]))) });

// Each note is [frequency Hz, start seconds, length seconds].
export const SOUND_CUES = Object.freeze({
  correct: freeze({ wave: "triangle", gain: 0.06, notes: [[523.25, 0, 0.18], [659.25, 0.1, 0.18], [783.99, 0.2, 0.2], [1046.5, 0.32, 0.36]] }),
  retry: freeze({ wave: "sine", gain: 0.035, notes: [[440, 0, 0.16], [369.99, 0.17, 0.26]] }),
  pop: freeze({ wave: "sine", gain: 0.045, notes: [[880, 0, 0.08], [1318.51, 0.06, 0.12]] }),
  tick: freeze({ wave: "sine", gain: 0.025, notes: [[1046.5, 0, 0.06]] }),
  whistle: freeze({ wave: "triangle", gain: 0.035, notes: [[587.33, 0, 0.3], [739.99, 0, 0.3], [587.33, 0.38, 0.5], [739.99, 0.38, 0.5]] }),
  fanfare: freeze({ wave: "triangle", gain: 0.055, notes: [[523.25, 0, 0.13], [523.25, 0.15, 0.13], [523.25, 0.3, 0.13], [659.25, 0.45, 0.3], [587.33, 0.78, 0.13], [659.25, 0.93, 0.13], [783.99, 1.08, 0.5]] }),
});

export function cueDuration(name) {
  const cue = SOUND_CUES[name];
  return cue ? Math.max(...cue.notes.map(([, start, length]) => start + length)) : 0;
}

// Schedules a cue on an AudioContext-like object. Returns false when nothing was played.
export function playCue(context, name) {
  const cue = Object.hasOwn(SOUND_CUES, name) ? SOUND_CUES[name] : null;
  if (!cue || !context?.createOscillator || !context.destination) return false;
  const now = Number(context.currentTime) || 0;
  for (const [frequency, start, length] of cue.notes) {
    const oscillator = context.createOscillator(), gain = context.createGain();
    oscillator.type = cue.wave;
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0, now + start);
    gain.gain.linearRampToValueAtTime(cue.gain, now + start + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, now + start + length);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start(now + start);
    oscillator.stop(now + start + length + 0.02);
  }
  return true;
}

export const PRAISE = Object.freeze(["太棒了！", "答對了！", "好厲害！", "真細心！", "你做到了！", "好棒的站長！"]);
export const ENCOURAGE = Object.freeze(["差一點點！", "再試一次！", "慢慢來！"]);

const pickFrom = (list, seed) => list[Math.abs(Math.trunc(Number(seed) || 0)) % list.length];
export const praiseWord = seed => pickFrom(PRAISE, seed);
export const encourageWord = seed => pickFrom(ENCOURAGE, seed);

const COLORS = Object.freeze(["#ff8a3d", "#ffc93c", "#3fbf7f", "#38a3e8", "#f2668b", "#9b6be8"]);
const SHAPES = Object.freeze(["star", "dot", "ribbon"]);
export const MAX_PARTICLES = 28;

// Deterministic so a re-render or a test produces the same burst.
function particleRandom(seed) {
  let value = (Math.trunc(Number(seed) || 1) >>> 0) || 1;
  return () => {
    value ^= value << 13; value >>>= 0;
    value ^= value >>> 17;
    value ^= value << 5; value >>>= 0;
    return value / 4294967296;
  };
}

export function burstMarkup({ seed = 1, reduced = false, count = 18, label = "" } = {}) {
  const safe = String(label).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  const praise = safe ? `<span class="praise-pop">${safe}</span>` : "";
  // Calm mode: the feedback text already carries the praise, so no overlay at all.
  if (reduced) return "";
  const random = particleRandom(seed), total = Math.max(0, Math.min(MAX_PARTICLES, Math.trunc(count) || 0));
  const particles = Array.from({ length: total }, (_, index) => {
    const angle = (index / Math.max(1, total)) * Math.PI * 2 + random() * 0.5;
    const distance = 90 + random() * 120;
    const x = Math.round(Math.cos(angle) * distance), y = Math.round(Math.sin(angle) * distance * 0.75 - 40);
    const rotation = Math.round(random() * 540 - 270), delay = Math.round(random() * 120);
    const shape = SHAPES[index % SHAPES.length], color = COLORS[index % COLORS.length];
    return `<i class="burst-${shape}" style="--x:${x}px;--y:${y}px;--r:${rotation}deg;--d:${delay}ms;--c:${color}"></i>`;
  }).join("");
  return `<div class="celebration-burst" aria-hidden="true">${particles}${praise}</div>`;
}

export function tripStars(trip) {
  const total = Array.isArray(trip?.questions) ? trip.questions.length : 0;
  const index = Number.isInteger(trip?.index) ? Math.max(0, Math.min(trip.index, total)) : 0;
  const earned = trip?.awarded ? total : Math.min(total, index + (trip?.solved ? 1 : 0));
  return { earned, total };
}

export function starRow(count, { esc = String } = {}) {
  const total = Math.max(0, Math.min(12, Math.trunc(count) || 0));
  if (!total) return "";
  return `<div class="finish-star-row" role="img" aria-label="${esc(`這趟收集了 ${total} 顆星星`)}">${Array.from({ length: total }, (_, index) => `<span style="--i:${index}">★</span>`).join("")}<small>這趟收集了 ${total} 顆星星</small></div>`;
}

// Bright, friendly passenger outfits; checked against the lightness/saturation gate in tests.
export const PASSENGER_OUTFITS = Object.freeze(["#f28c38", "#2f9ad6", "#58b368", "#e2577f", "#8d63d2", "#e0b31f"]);
export const PASSENGER_SKIN = Object.freeze(["#f2c29b", "#c98e6b", "#e0a882"]);
