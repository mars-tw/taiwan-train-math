import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { GAMES, LEVELS } from "../src/engine.js";
import { homeMarkup, playroomMarkup, PLAYROOM_CATEGORIES } from "../src/home.js";
import { journeyMarkup } from "../src/journeys.js";
const trains = [{ id: "emu3000", cardLabel: "EMU3000 新自強號", name: "新自強號" }, { id: "700t", cardLabel: "台灣高鐵 700T", name: "台灣高鐵" }];
const picture = train => `<img src="assets/images/${train.id}.webp" alt="${train.name}">`;
const count = (markup, expression) => [...markup.matchAll(expression)].length;

test("home keeps the original story once and one compact departure without repeated game selection", () => {
  const markup = homeMarkup({ trains, selected: "emu3000", progress: { level: "small" }, image: picture });
  assert.ok(markup.startsWith('<section class="story-scene"'));
  assert.equal(count(markup, /id="story-scene"/g), 1); assert.equal(count(markup, /id="departure"/g), 1);
  assert.match(markup, /<span id="railway-map"[^>]*><\/span>/);
  assert.equal(count(markup, /id="lobby-start"/g), 1); assert.match(markup, /驚喜旅程，/); assert.match(markup, /出發！/); assert.match(markup, /href="#playroom"/);
  assert.match(markup, /data-detail="emu3000"/); assert.match(markup, /data-speak="emu3000"/); assert.match(markup, /href="#collection"/); assert.match(markup, /3–4 歲/);
  assert.doesNotMatch(markup, /class="railway-world|new-adventures|boarding-pass|featured-trains|mission-hall|passport-invite|data-mission=|id="practice-select"|data-level=/);
});

test("a saved trip has a separate priority resume while a new surprise remains available", () => {
  const markup = homeMarkup({ trains, progress: { level: "small" }, image: picture, resume: { train: trains[1], level: "large", index: 2, total: 5 } });
  assert.equal(count(markup, /id="journey-resume"/g), 1); assert.ok(markup.indexOf('id="journey-resume"') < markup.indexOf('id="lobby-start"'));
  assert.match(markup, /繼續剛剛的旅程/); assert.match(markup, /台灣高鐵 700T · 7–8 歲 · 第 3／5 站/);
  for (const resume of [null, { index: -1, total: 3 }, { index: 3, total: 3 }, { index: 0, total: 0 }]) assert.doesNotMatch(homeMarkup({ trains, progress: { level: "small" }, resume }), /id="journey-resume"/);
  const playroom = playroomMarkup({ trains, progress: { level: "small" }, resume: { train: trains[1], level: "large", index: 2, total: 5 } });
  assert.match(playroom, /<section class="playroom-page" id="playroom"/);
  assert.equal(count(playroom, /id="journey-resume"/g), 1);
  assert.ok(playroom.indexOf('id="journey-resume"') < playroom.indexOf('role="tablist"'));
  assert.equal(count(playroom, /data-mission=/g), 20);
});

test("four categories partition all twenty engine games without repeated launch controls", () => {
  assert.deepEqual(PLAYROOM_CATEGORIES.map(group => group.name), ["數學", "觀察與記憶", "拼搭與方向", "生活與分享"]);
  const grouped = PLAYROOM_CATEGORIES.flatMap(group => group.games);
  assert.equal(grouped.length, 20); assert.equal(new Set(grouped).size, 20); assert.deepEqual([...grouped].sort(), Object.keys(GAMES).sort());
  for (const level of Object.keys(LEVELS)) {
    const markup = playroomMarkup({ progress: { level } }), launches = [...markup.matchAll(/data-mission="([^"]+)"/g)].map(match => match[1]);
    assert.equal(launches.length, 20); assert.equal(new Set(launches).size, 20); assert.deepEqual([...launches].sort(), grouped.slice().sort());
    assert.equal(count(markup, /role="tab"/g), 4); assert.equal(count(markup, /role="tabpanel"/g), 4); assert.equal(count(markup, /role="tabpanel"[^>]* hidden/g), 3);
    assert.match(markup, new RegExp(`data-game-category="${level === "small" ? "build" : "math"}" aria-selected="true"`));
    assert.match(markup, /<h1 id="playroom-title">遊戲室/); assert.match(markup, /id="quick-settings"/); assert.doesNotMatch(markup, /id="story-scene"|id="practice-select"/);
  }
});

test("tab selection has matching panel semantics and unavailable age games remain honest", () => {
  for (const category of PLAYROOM_CATEGORIES) {
    const markup = playroomMarkup({ progress: { level: "small" }, category: category.id });
    assert.match(markup, new RegExp(`id="playroom-tab-${category.id}"[^>]*aria-selected="true"[^>]*aria-controls="playroom-panel-${category.id}"[^>]*tabindex="0"`));
    assert.doesNotMatch(markup.match(new RegExp(`<section[^>]*id="playroom-panel-${category.id}"[^>]*>`))[0], / hidden/);
    for (const id of ["boarding", "compare", "clock"]) assert.match(markup, new RegExp(`data-mission="${id}" aria-label="[^\"]*適合 5–8 歲，查看提示`));
  }
  assert.match(playroomMarkup({ progress: { level: "small" }, category: "unknown" }), /data-game-category="build" aria-selected="true"/);
});

test("six routes live only in a closed disclosure without duplicate legacy anchors", () => {
  let actualOptions;
  const markup = playroomMarkup({ progress: { level: "medium", journeysCompleted: ["forest"] }, journeyMarkup: options => { actualOptions = options; return journeyMarkup(options); } });
  assert.match(markup, /<details class="playroom-journeys" id="theme-journeys">/); assert.doesNotMatch(markup, /<details[^>]*\bopen\b/);
  assert.equal(count(markup, /id="theme-journeys"/g), 1); assert.match(markup, /id="theme-journeys-routes"/); assert.equal(count(markup, /data-journey=/g), 6);
  assert.equal(actualOptions.level, "medium"); assert.deepEqual(actualOptions.completed, ["forest"]); assert.ok(actualOptions.availableGames.includes("tickets"));
  assert.equal(count(playroomMarkup({ progress: { level: "small" }, routeMarkup: journeyMarkup({ level: "small" }) }), /data-journey=/g), 6);
});

test("selected names are escaped and missing saved choices have a safe fallback", () => {
  const markup = homeMarkup({ trains: [{ id: 'train"x', cardLabel: '<img src=x onerror=alert(1)>', name: "測試車" }], selected: "missing", progress: { level: "__proto__" } });
  assert.match(markup, /data-detail="train&quot;x"/); assert.doesNotMatch(markup, /<img src=x onerror/); assert.match(markup, /&lt;img src=x onerror=alert\(1\)&gt;/); assert.match(markup, /3–4 歲/);
  assert.match(homeMarkup(), /挑一台喜歡的列車/); assert.match(playroomMarkup({ trains, selected: "700t", progress: { level: "large" } }), /陪你出發：<strong>台灣高鐵 700T/);
});

test("lobby uses native keyboard elements and child-sized bounded layouts", () => {
  for (const markup of [homeMarkup({ trains, progress: { level: "small" } }), playroomMarkup({ progress: { level: "large" }, journeyMarkup })]) {
    const component = markup.slice(markup.indexOf('class="lobby-content"') >= 0 ? markup.indexOf('class="lobby-content"') : 0);
    assert.ok([...component.matchAll(/<button\b[^>]*>/g)].every(match => match[0].includes('type="button"'))); assert.doesNotMatch(component, /onclick=|onfocus=|autofocus/);
  }
  const css = readFileSync(new URL("../src/lobby.css", import.meta.url), "utf8");
  assert.match(css, /min-width: 48px/); assert.match(css, /min-height: 48px/); assert.match(css, /\.playroom-game-panel\[hidden\] \{ display: none/);
  assert.match(css, /repeat\(2, minmax\(0, 1fr\)\)/); assert.match(css, /max-width: 600px/);
});
