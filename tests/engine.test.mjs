import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import {
  LEVELS,
  questionFor,
  createTrip,
  seededRandom,
  isCorrect,
  readProgress,
  saveProgress,
  defaults,
} from "../src/engine.js";
const { trains } = JSON.parse(
  readFileSync(new URL("../data/trains.json", import.meta.url), "utf8"),
);
test("catalogue has unique identities, source links and image assets", () => {
  assert.equal(new Set(trains.map((t) => t.id)).size, trains.length);
  for (const t of trains) {
    for (const k of [
      "id",
      "name",
      "model",
      "intro",
      "fact",
      "category",
      "modelKind",
      "imageKind",
    ])
      assert.ok(t[k], `${t.id}: ${k}`);
    assert.ok(existsSync(t.image), t.image);
    assert.ok(t.sources.every((s) => s.startsWith("https://")));
    assert.ok(["type", "fleet", "name"].includes(t.modelKind));
  }
  assert.ok(trains.find((t) => t.id === "l0" && t.status === "experimental"));
  assert.ok(trains.find((t) => t.id === "n700st" && t.status === "future"));
});
test("generated maths remain correct, distinct and within each age range", () => {
  for (const level of Object.keys(LEVELS))
    for (let seed = 0; seed < 500; seed++) {
      const trip = createTrip({
        level,
        train: trains[seed % trains.length],
        trains,
        rng: seededRandom(seed),
        challenge: seed % 2 === 0,
      });
      assert.equal(trip.length, LEVELS[level].stops);
      for (const q of trip) {
        assert.equal(isCorrect(q, q.answer), true);
        if (q.choices) {
          assert.equal(new Set(q.choices).size, q.choices.length);
          assert.ok(q.choices.includes(q.answer));
        }
        if (q.game === "count" || q.game === "boarding") {
          assert.ok(q.answer >= 0 && q.answer <= LEVELS[level].max);
          assert.ok(q.choices.every((x) => x >= 0 && x <= LEVELS[level].max));
        }
        if (q.game === "boarding") {
          assert.equal(
            q.answer,
            q.operation === "add" ? q.start + q.change : q.start - q.change,
          );
          assert.ok(q.change >= 0);
        }
        if (q.game === "order") {
          assert.deepEqual(
            [...q.numbers].sort((a, b) => a - b),
            q.answer,
          );
          assert.ok(q.answer.every((x) => x >= 0 && x <= LEVELS[level].max));
          assert.equal(isCorrect(q, [...q.answer].reverse()), false);
        }
        if (q.game === "compare")
          assert.equal(
            q.answer,
            q.left === q.right ? "equal" : q.left > q.right ? "left" : "right",
          );
      }
      if (level === "small")
        assert.deepEqual(
          trip.map((q) => q.game),
          ["count", "identify", "order"],
        );
    }
});
test("recognition avoids identical family images and ambiguous same models", () => {
  for (const t of trains) {
    const q = questionFor({
      level: "large",
      game: "identify",
      train: t,
      trains,
      rng: seededRandom(42),
    });
    assert.equal(q.choices.length, 3);
    for (const id of q.choices.filter((id) => id !== t.id)) {
      const other = trains.find((t) => t.id === id);
      assert.notEqual(other.image, t.image);
      assert.notEqual(other.model, t.model);
      assert.notEqual(other.status, "future");
    }
  }
});
test("damaged or blocked storage never prevents play", () => {
  assert.deepEqual(readProgress({ getItem: () => "{broken" }), defaults());
  assert.deepEqual(
    readProgress({
      getItem: () => {
        throw Error();
      },
    }),
    defaults(),
  );
  assert.equal(
    saveProgress(
      {
        setItem: () => {
          throw Error();
        },
      },
      defaults(),
    ),
    false,
  );
  const valid = readProgress({
    getItem: () =>
      JSON.stringify({
        version: 1,
        level: "bogus",
        trips: -3,
        completed: ["e5", "e5", 42],
        voice: "true",
      }),
  });
  assert.equal(valid.level, "small");
  assert.equal(valid.trips, 0);
  assert.equal(valid.voice, false);
  assert.deepEqual(valid.completed, ["e5"]);
});
test("practice mode and unsupported age choices are explicit", () => {
  assert.throws(() =>
    questionFor({ level: "small", game: "boarding", train: trains[0], trains }),
  );
  const trip = createTrip({
    level: "medium",
    train: trains[0],
    trains,
    practice: "count",
  });
  assert.ok(trip.every((q) => q.game === "count"));
});
