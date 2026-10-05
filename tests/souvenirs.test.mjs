import test from "node:test";
import assert from "node:assert/strict";
import { SOUVENIRS, SOUVENIR_THEMES, giftChoices, pickSouvenir } from "../src/adventure.js";
import { souvenirMarkup, souvenirCollection, giftDetailMarkup } from "../src/adventure-ui.js";
import { readProgress, seededRandom } from "../src/engine.js";

const legacyIds = [
  "star-letter", "lighthouse", "forest-leaf", "cloud", "ticket", "apple",
  "mountain", "bird", "clock", "rainbow", "shell", "spark",
];
test("the souvenir book has six complete themes and keeps every old passport gift", () => {
  assert.equal(SOUVENIRS.length, 36);
  assert.equal(new Set(SOUVENIRS.map((item) => item.id)).size, 36);
  assert.equal(SOUVENIR_THEMES.length, 6);
  assert.equal(new Set(SOUVENIR_THEMES.map((theme) => theme.id)).size, 6);
  const themes = new Set(SOUVENIR_THEMES.map((theme) => theme.id));
  const playKinds = new Set(["signal", "wind", "stamp", "glow", "bounce"]);
  for (const item of SOUVENIRS) {
    assert.match(item.id, /^[a-z]+(?:-[a-z]+)*$/);
    for (const field of ["icon", "name", "story"]) assert.ok(item[field]?.trim());
    assert.ok(themes.has(item.theme));
    assert.ok(playKinds.has(item.playKind));
  }
  for (const theme of SOUVENIR_THEMES) {
    assert.ok(theme.name && theme.icon && theme.description);
    assert.equal(SOUVENIRS.filter((item) => item.theme === theme.id).length, 6);
  }
  const progress = readProgress({ getItem: () => JSON.stringify({
    version: 1, trips: 12, souvenirs: [...legacyIds, "missing", "ticket"],
  }) });
  assert.deepEqual(progress.souvenirs, legacyIds);
  assert.equal(progress.trips, 12);
});

test("opening a gift offers three different new gifts from three themes when possible", () => {
  const progress = { trips: 20, souvenirs: legacyIds };
  const before = JSON.stringify(progress);
  for (let seed = 0; seed < 100; seed++) {
    const choices = giftChoices(progress, "700t", seededRandom(seed));
    assert.equal(choices.length, 3);
    assert.equal(new Set(choices.map((item) => item.id)).size, 3);
    assert.equal(new Set(choices.map((item) => item.theme)).size, 3);
    assert.ok(choices.every((item) => !progress.souvenirs.includes(item.id)));
    assert.ok(choices.every((item) => SOUVENIRS.includes(item)));
  }
  assert.equal(JSON.stringify(progress), before, "opening does not claim a gift");
  assert.deepEqual(
    giftChoices(progress, "700t", seededRandom(71)),
    giftChoices(progress, "700t", seededRandom(71)),
  );
});

test("near completion only uncollected gifts are offered, even with fewer themes", () => {
  for (const remainingIds of [
    ["signal"],
    ["signal", "station-sign"],
    ["signal", "station-sign", "whistle"],
    ["signal", "station-sign", "windmill"],
  ]) {
    const progress = { trips: 35, souvenirs: SOUVENIRS.map((item) => item.id)
      .filter((id) => !remainingIds.includes(id)) };
    const choices = giftChoices(progress, "700t", () => 0);
    assert.equal(choices.length, remainingIds.length);
    assert.deepEqual(new Set(choices.map((item) => item.id)), new Set(remainingIds));
    assert.equal(new Set(choices.map((item) => item.theme)).size,
      new Set(SOUVENIRS.filter((item) => remainingIds.includes(item.id)).map((item) => item.theme)).size);
  }
});

test("a full book still offers playable gifts and single-gift compatibility fills a book", () => {
  const progress = { trips: 0, souvenirs: [] };
  for (let trip = 0; trip < SOUVENIRS.length; trip++) {
    progress.trips++;
    const item = pickSouvenir(progress, "700t");
    assert.ok(!progress.souvenirs.includes(item.id));
    progress.souvenirs.push(item.id);
  }
  assert.equal(new Set(progress.souvenirs).size, 36);
  const choices = giftChoices(progress, "700t", seededRandom(4));
  assert.equal(choices.length, 3);
  assert.equal(new Set(choices.map((item) => item.id)).size, 3);
  assert.equal(new Set(choices.map((item) => item.theme)).size, 3);
  assert.ok(SOUVENIRS.includes(pickSouvenir(progress, "700t")));
});

test("gift markup opens an envelope, offers choices, then only lets the chosen gift play", () => {
  const closed = souvenirMarkup({ giftChoices: [] });
  assert.match(closed, /id="gift-open"/);
  assert.doesNotMatch(closed, /data-gift-choice=/);
  const choices = giftChoices({ souvenirs: [] }, "700t", seededRandom(5));
  const opened = souvenirMarkup({ giftChoices: choices });
  assert.equal((opened.match(/data-gift-choice=/g) || []).length, 3);
  for (const item of choices) assert.ok(opened.includes(`data-gift-choice="${item.id}"`));
  const claimed = souvenirMarkup({ gift: choices[0], giftChoices: choices });
  assert.doesNotMatch(claimed, /data-gift-choice=|id="gift-open"/);
  assert.match(claimed, /data-play-gift=/);
  assert.match(claimed, /id="trip-gift-title"/);
  assert.doesNotMatch(claimed, /id="gift-detail-title"/);
});

test("the book shows all slots, hides unknown names and awards only complete theme stamps", () => {
  const empty = souvenirCollection({ souvenirs: [] });
  assert.equal((empty.match(/class="souvenir-slot gift-locked"/g) || []).length, 36);
  assert.equal((empty.match(/<progress /g) || []).length, 6);
  assert.doesNotMatch(empty, /data-inspect-gift=|souvenir-set-stamp/);
  assert.doesNotMatch(empty, /星光信封|海邊燈塔/);
  const station = SOUVENIRS.filter((item) => item.theme === "station");
  const progress = { souvenirs: [...station.map((item) => item.id), "apple", "ticket", "missing"] };
  const book = souvenirCollection(progress);
  assert.match(book, /<strong>7 \/ 36<\/strong>/);
  assert.equal((book.match(/data-inspect-gift=/g) || []).length, 7);
  assert.equal((book.match(/class="souvenir-slot gift-locked"/g) || []).length, 29);
  assert.equal((book.match(/class="souvenir-set-stamp"/g) || []).length, 1);
  assert.match(book, /車站工具已收藏 6 款，共 6 款/);
  assert.match(book, /旅途美味已收藏 1 款，共 6 款/);
  const full = souvenirCollection({ souvenirs: SOUVENIRS.map((item) => item.id) });
  assert.equal((full.match(/class="souvenir-set-stamp"/g) || []).length, 6);
});

test("every gift has a vector toy, named dialog and accessible action feedback", () => {
  const art = new Set();
  for (const item of SOUVENIRS) {
    const html = giftDetailMarkup(item);
    assert.match(html, /<svg class="gift-svg"/);
    assert.match(html, /id="gift-detail-title"/);
    assert.ok(html.includes(`data-play-gift="${item.id}"`));
    assert.ok(html.includes(`data-play-kind="${item.playKind}"`));
    assert.match(html, /data-gift-feedback role="status" aria-live="polite"/);
    art.add(html.match(/<svg class="gift-svg"[\s\S]*?<\/svg>/)[0]);
  }
  assert.equal(art.size, 36);
  const escaped = giftDetailMarkup({ ...SOUVENIRS[0], name: '<img src=x onerror="bad()">', story: "<script>bad()</script>" });
  assert.doesNotMatch(escaped, /<img |<script>/);
  assert.match(escaped, /&lt;img /);
});
