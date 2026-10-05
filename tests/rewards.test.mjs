import test from "node:test";
import assert from "node:assert/strict";
import { SOUVENIRS } from "../src/adventure.js";
import { defaults, readProgress, saveProgress, seededRandom } from "../src/engine.js";
import { enqueueGift, offerGifts, claimGift } from "../src/rewards.js";

test("unopened rewards accumulate without granting or losing gifts", () => {
  const progress = defaults();
  for (let i = 0; i < 3; i++) {
    progress.trips++;
    enqueueGift(progress);
  }
  assert.equal(progress.giftCredits, 3);
  assert.deepEqual(progress.souvenirs, []);
  let data;
  saveProgress({ setItem: (_key, value) => { data = value; } }, progress);
  const restored = readProgress({ getItem: () => data });
  assert.equal(restored.giftCredits, 3);
  assert.deepEqual(restored.souvenirs, []);
});

test("offered choices remain fixed across reopen and reload, then claim spends only one credit", () => {
  const progress = { ...defaults(), trips: 2 };
  enqueueGift(progress);
  enqueueGift(progress);
  const offered = offerGifts(progress, "700t", seededRandom(3));
  assert.equal(offered.length, 3);
  assert.deepEqual(offerGifts(progress, "e5", seededRandom(17)), offered);
  const restored = readProgress({ getItem: () => JSON.stringify(progress) });
  assert.deepEqual(offerGifts(restored, "e5", seededRandom(17)).map(gift => gift.id), offered.map(gift => gift.id));
  const gift = claimGift(restored, offered[0].id);
  assert.equal(gift.id, offered[0].id);
  assert.equal(restored.giftCredits, 1);
  assert.deepEqual(restored.souvenirs, [gift.id]);
  assert.deepEqual(restored.giftOffer, []);
  assert.equal(claimGift(restored, gift.id), null);
  assert.equal(restored.giftCredits, 1);
  assert.ok(offerGifts(restored, "e5").every(item => item.id !== gift.id));
});

test("invalid or unearned claims never consume credit or create a collectible", () => {
  const progress = defaults();
  assert.deepEqual(offerGifts(progress, "700t"), []);
  assert.equal(claimGift(progress, SOUVENIRS[0].id), null);
  progress.trips++;
  enqueueGift(progress);
  const choices = offerGifts(progress, "700t", seededRandom(3));
  const outside = SOUVENIRS.find(item => !choices.some(gift => gift.id === item.id));
  assert.equal(claimGift(progress, "unknown"), null);
  assert.equal(claimGift(progress, outside.id), null);
  assert.equal(progress.giftCredits, 1);
  assert.deepEqual(progress.souvenirs, []);
});

test("rewards cover the whole collection before repeating and remain playable after completion", () => {
  const progress = defaults();
  for (let i = 0; i < SOUVENIRS.length; i++) {
    progress.trips++;
    enqueueGift(progress);
    const offer = offerGifts(progress, "700t", seededRandom(i));
    assert.ok(offer.length >= 1 && offer.length <= 3);
    assert.ok(offer.every(gift => !progress.souvenirs.includes(gift.id)));
    assert.ok(claimGift(progress, offer[0].id));
  }
  assert.equal(progress.souvenirs.length, SOUVENIRS.length);
  progress.trips++;
  enqueueGift(progress);
  const offer = offerGifts(progress, "700t", seededRandom(99));
  assert.equal(offer.length, 3);
  assert.ok(claimGift(progress, offer[0].id));
  assert.equal(progress.giftCredits, 0);
  assert.equal(progress.souvenirs.length, SOUVENIRS.length);
});

test("old saves keep their collection; corrupt pending fields are bounded and discarded safely", () => {
  const old = readProgress({ getItem: () => JSON.stringify({ version: 1, trips: 7, souvenirs: ["ticket", "spark"] }) });
  assert.deepEqual(old.souvenirs, ["ticket", "spark"]);
  assert.equal(old.giftCredits, 0);
  assert.deepEqual(old.giftOffer, []);
  for (const giftCredits of [-1, 1.5, "3", null]) {
    const restored = readProgress({ getItem: () => JSON.stringify({ version: 1, trips: 2, giftCredits, giftOffer: ["ticket"] }) });
    assert.equal(restored.giftCredits, 0);
    assert.deepEqual(restored.giftOffer, []);
  }
  const restored = readProgress({ getItem: () => JSON.stringify({ version: 1, trips: 2, giftCredits: 99, giftOffer: ["ticket", "ticket", {}, "bad", "signal", "spark", "apple"] }) });
  assert.equal(restored.giftCredits, 2);
  assert.deepEqual(restored.giftOffer, ["ticket", "signal", "spark"]);
});
