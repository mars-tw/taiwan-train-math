import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  SOUND_CUES, cueDuration, playCue, PRAISE, ENCOURAGE, praiseWord, encourageWord,
  burstMarkup, MAX_PARTICLES, tripStars, starRow, PASSENGER_OUTFITS, PASSENGER_SKIN,
} from "../src/celebration.js";
import { storyMarkup } from "../src/story.js";

const read = path => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

function fakeContext() {
  const log = [];
  const param = name => ({ value: 0, setValueAtTime: (v, t) => log.push([name, "set", v, t]), linearRampToValueAtTime: (v, t) => log.push([name, "ramp", v, t]), exponentialRampToValueAtTime: (v, t) => log.push([name, "exp", v, t]) });
  return {
    log, currentTime: 2, destination: {},
    createOscillator() { const o = { type: "", frequency: param("frequency"), connect: next => next, start: t => log.push(["start", t]), stop: t => log.push(["stop", t]) }; log.push(["osc", o]); return o; },
    createGain() { const g = { gain: param("gain"), connect: () => this.destination }; return g; },
  };
}

test("sound cues are short, quiet and the retry cue is gentler than the success cue", () => {
  for (const name of ["correct", "retry", "pop", "tick", "whistle", "fanfare"]) {
    const cue = SOUND_CUES[name];
    assert.ok(cue, name);
    assert.ok(cue.gain > 0 && cue.gain <= 0.07, `${name} gain`);
    assert.ok(["sine", "triangle"].includes(cue.wave), `${name} uses a soft waveform`);
    assert.ok(cueDuration(name) > 0 && cueDuration(name) <= 1.6, `${name} duration`);
    assert.ok(Object.isFrozen(cue) && Object.isFrozen(cue.notes));
  }
  assert.ok(SOUND_CUES.retry.gain < SOUND_CUES.correct.gain);
  assert.equal(SOUND_CUES.retry.wave, "sine");
  assert.ok(cueDuration("pop") <= 0.3 && cueDuration("tick") <= 0.1);
  assert.equal(cueDuration("missing"), 0);
});

test("playCue schedules every note from the context clock and ignores unknown cues", () => {
  const context = fakeContext();
  assert.equal(playCue(context, "correct"), true);
  const oscillators = context.log.filter(entry => entry[0] === "osc").map(entry => entry[1]);
  assert.equal(oscillators.length, SOUND_CUES.correct.notes.length);
  assert.deepEqual(oscillators.map(o => o.frequency.value), SOUND_CUES.correct.notes.map(note => note[0]));
  assert.ok(oscillators.every(o => o.type === "triangle"));
  const starts = context.log.filter(entry => entry[0] === "start").map(entry => entry[1]);
  assert.deepEqual(starts, SOUND_CUES.correct.notes.map(note => 2 + note[1]));
  assert.equal(playCue(context, "toString"), false);
  assert.equal(playCue(context, "nope"), false);
  assert.equal(playCue(null, "correct"), false);
});

test("praise and encouragement rotate deterministically and never scold", () => {
  assert.ok(PRAISE.length >= 4 && ENCOURAGE.length >= 2);
  assert.equal(praiseWord(3), praiseWord(3));
  assert.notEqual(praiseWord(0), praiseWord(1));
  assert.ok(PRAISE.includes(praiseWord(-7)) && PRAISE.includes(praiseWord("x")));
  assert.ok(ENCOURAGE.includes(encourageWord(12345)));
  for (const word of [...PRAISE, ...ENCOURAGE]) assert.doesNotMatch(word, /錯|笨|失敗|扣/);
});

test("the burst is decorative, bounded, deterministic and absent in calm mode", () => {
  const markup = burstMarkup({ seed: 42, label: "太棒了！" });
  assert.match(markup, /^<div class="celebration-burst" aria-hidden="true">/);
  assert.equal([...markup.matchAll(/<i class="burst-/g)].length, 18);
  assert.match(markup, /<span class="praise-pop">太棒了！<\/span>/);
  assert.equal(markup, burstMarkup({ seed: 42, label: "太棒了！" }));
  assert.notEqual(markup, burstMarkup({ seed: 43, label: "太棒了！" }));
  assert.equal([...burstMarkup({ count: 999 }).matchAll(/<i /g)].length, MAX_PARTICLES);
  assert.equal(burstMarkup({ reduced: true, label: "太棒了！" }), "");
  assert.match(burstMarkup({ label: '<img src=x onerror="1">' }), /&lt;img src=x onerror=&quot;1&quot;&gt;/);
  assert.doesNotMatch(markup, /https?:|url\(/);
});

test("stars equal finished stations and the finish row reports them", () => {
  const questions = [{}, {}, {}];
  assert.deepEqual(tripStars({ questions, index: 0, solved: false }), { earned: 0, total: 3 });
  assert.deepEqual(tripStars({ questions, index: 1, solved: true }), { earned: 2, total: 3 });
  assert.deepEqual(tripStars({ questions, index: 2, solved: true, awarded: true }), { earned: 3, total: 3 });
  assert.deepEqual(tripStars(null), { earned: 0, total: 0 });
  const row = starRow(3);
  assert.equal([...row.matchAll(/★/g)].length, 3);
  assert.match(row, /這趟收集了 3 顆星星/);
  assert.equal(starRow(0), "");
  assert.equal([...starRow(99).matchAll(/<span /g)].length, 12);
});

function hsl(hex) {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
  const s = max === min ? 0 : (max - min) / (1 - Math.abs(2 * l - 1));
  return { s, l };
}

test("passenger outfits pass the brightness and saturation gate", () => {
  assert.ok(PASSENGER_OUTFITS.length >= 4 && PASSENGER_SKIN.length >= 3);
  for (const color of PASSENGER_OUTFITS) {
    const { s, l } = hsl(color);
    assert.ok(s >= 0.32, `${color} saturation ${s.toFixed(2)}`);
    assert.ok(l >= 0.3 && l <= 0.75, `${color} lightness ${l.toFixed(2)}`);
  }
  const app = read("src/app.js");
  assert.match(app, /PASSENGER_OUTFITS\[i % PASSENGER_OUTFITS\.length\]/);
  assert.match(app, /cx="20\.5" cy="14" r="1\.6"/, "passengers have eyes");
});

test("home shows one large start button in the story that uses the normal departure", () => {
  const story = storyMarkup();
  assert.equal([...story.matchAll(/id="hero-play"/g)].length, 1);
  assert.match(story, /<button type="button" id="hero-play" class="story-play">/);
  assert.match(story, /開始玩！/);
  assert.ok(story.indexOf('id="hero-play"') < story.indexOf('id="story-toggle"'), "start comes before story controls");
  assert.match(story, /href="#departure"/);
  const app = read("src/app.js");
  assert.match(app, /case "hero-play":\s*case "lobby-start":\s*practice = starterPractice\(progress\);/);
});

test("game feedback wiring: celebrate, retry nudge, pops, whistle and fanfare", () => {
  const app = read("src/app.js");
  assert.match(app, /trip\.celebrate = true;\s*chime\(\);/);
  assert.match(app, /cue\("retry"\)/);
  assert.match(app, /cue\("whistle"\)/);
  assert.match(app, /cue\("fanfare"\)/);
  assert.ok([...app.matchAll(/cue\("pop"\)/g)].length >= 3);
  assert.match(app, /burstMarkup\(\{ seed: trip\.meta\.seed \+ trip\.index \* 7919, reduced: motionReduced\(\)/);
  assert.match(app, /trip\.celebrate = false; trip\.retryPulse = false; trip\.glideFrom = null;/, "one-shot effects are cleared after the render");
  assert.doesNotMatch(read("src/celebration.js"), /fetch\(|XMLHttpRequest|https?:\/\//);
});

test("celebration styles are linked, honour reduced motion and never block taps", () => {
  const html = read("index.html"), css = read("src/celebration.css");
  assert.match(html, /<link rel="stylesheet" href="src\/celebration\.css\?v=1\.14\.0" \/>/);
  assert.ok(html.indexOf("learning.css") < html.indexOf("celebration.css"));
  assert.match(css, /\.celebration-burst \{[^}]*pointer-events: none;/);
  assert.match(css, /\.celebration-burst \{[^}]*inset: 0;[^}]*overflow: hidden;/, "particles are clipped so phones never scroll sideways");
  assert.match(css, /\.reduced-motion \.celebration-burst \{ display: none; \}/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css, /\.header-actions \.icon-btn,\s*\.game-tools \.icon-btn \{ min-width: 48px; min-height: 48px; \}/);
  assert.match(css, /\.in-game \.question-actions \{\s*position: sticky;/);
  assert.doesNotMatch(css, /url\(|@import|https?:/);
});
