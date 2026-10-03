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
  allowedGames,
  newMemoryState,
  memoryTurn,
  SHAPES,
  clockLabel,
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
        assert.ok(trip.every((q) => allowedGames("small").includes(q.game)));
    }
});
test("new activities generate solvable and age-appropriate tasks", () => {
  for (const level of Object.keys(LEVELS)) {
    for (let seed = 0; seed < 300; seed++) {
      for (const game of ["pattern", "cargo", "memory", "clock"].filter((g) =>
        allowedGames(level).includes(g),
      )) {
        const q = questionFor({
          level,
          game,
          train: trains[seed % trains.length],
          trains,
          rng: seededRandom(seed),
        });
        assert.equal(isCorrect(q, q.answer), true);
        if (q.choices) {
          assert.equal(new Set(q.choices).size, q.choices.length);
          assert.ok(q.choices.includes(q.answer));
          for (const wrong of q.choices.filter((v) => v !== q.answer))
            assert.equal(isCorrect(q, wrong), false);
        }
        if (game === "cargo") {
          assert.ok(q.answer >= 1 && q.answer <= LEVELS[level].max);
          assert.equal(q.max, LEVELS[level].max);
        }
        if (game === "pattern" && q.kind === "shape") {
          assert.ok(
            q.sequence.every((v, i) => v === q.unit[i % q.unit.length]),
          );
          assert.equal(q.answer, q.unit[q.sequence.length % q.unit.length]);
          assert.ok(q.choices.every((v) => SHAPES[v]));
          if (level === "small") assert.equal(q.unit.length, 2);
        }
        if (game === "pattern" && q.kind === "number") {
          assert.ok(
            q.sequence.every(
              (v, i) =>
                i === 0 || Number(v) - Number(q.sequence[i - 1]) === q.step,
            ),
          );
          assert.equal(Number(q.answer) - Number(q.sequence.at(-1)), q.step);
          assert.ok(Number(q.answer) <= 20);
        }
        if (game === "clock") {
          assert.ok(q.hour >= 1 && q.hour <= 12);
          assert.ok(q.minute === 0 || (level === "large" && q.minute === 30));
          assert.equal(q.answer, q.hour * 60 + q.minute);
          assert.ok(
            q.choices.every(
              (v) => v >= 60 && v <= 750 && [0, 30].includes(v % 60),
            ),
          );
          assert.equal(
            clockLabel(q.answer),
            `${q.hour} 點${q.minute ? "半" : "整"}`,
          );
        }
        if (game === "memory") {
          assert.equal(
            q.pairs.length,
            { small: 2, medium: 3, large: 4 }[level],
          );
          assert.equal(
            new Set(q.pairs.map((id) => trains.find((t) => t.id === id).image))
              .size,
            q.pairs.length,
          );
          assert.equal(q.deck.length, q.pairs.length * 2);
          let state = newMemoryState();
          for (const id of q.pairs) {
            const pair = q.deck.flatMap((v, i) => (v === id ? [i] : []));
            assert.equal(pair.length, 2);
            state = memoryTurn(
              memoryTurn(state, pair[0], q.deck),
              pair[1],
              q.deck,
            );
          }
          assert.equal(state.matched.length, q.deck.length);
          assert.equal(isCorrect(q, state.matched.length / 2), true);
        }
      }
    }
  }
});
test("memory blocks repeat flips, out-of-range input and a third unmatched card", () => {
  const deck = ["a", "b", "a", "b"];
  let state = newMemoryState();
  assert.equal(memoryTurn(state, -1, deck), state);
  assert.equal(memoryTurn(state, 4, deck), state);
  state = memoryTurn(state, 0, deck);
  assert.equal(memoryTurn(state, 0, deck), state);
  state = memoryTurn(state, 1, deck);
  assert.deepEqual(state.matched, []);
  assert.equal(memoryTurn(state, 2, deck), state);
  state = { ...state, open: [] };
  state = memoryTurn(memoryTurn(state, 0, deck), 2, deck);
  assert.deepEqual(state.matched, [0, 2]);
  assert.equal(memoryTurn(state, 0, deck), state);
});
test("mixed journeys vary while always teaching numbers and the chosen train", () => {
  for (const level of Object.keys(LEVELS)) {
    const seen = new Set();
    for (let seed = 0; seed < 100; seed++) {
      const trip = createTrip({
        level,
        train: trains[0],
        trains,
        rng: seededRandom(Math.imul(seed, 2654435761)),
      });
      assert.equal(trip[0].game, "count");
      assert.equal(trip.at(-1).game, "identify");
      assert.equal(new Set(trip.map((q) => q.game)).size, trip.length);
      for (const q of trip) seen.add(q.game);
    }
    assert.deepEqual([...seen].sort(), allowedGames(level).sort());
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
