import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { LEVELS, allowedGames, createTrip, seededRandom, newMemoryState, questionSignature } from "../src/engine.js";
import { newAdventureState } from "../src/adventure.js";
import { newPuzzleState } from "../src/puzzle.js";
import { newExplorerState, moveMaze, MAZE_DIRECTIONS } from "../src/explorers.js";
import { newWorkshopState, appendCommand, addWeight, PROGRAM_DIRECTIONS } from "../src/workshop.js";
import { newDiscoveryState, selectMosaicColor, paintMosaicCell, findDifference } from "../src/discovery.js";
import { newTicketsState, payToken } from "../src/tickets.js";
import { TRIP_SESSION_KEY, saveTripSession, readTripSession, clearTripSession } from "../src/trip-session.js";

const { trains } = JSON.parse(readFileSync(new URL("../data/trains.json", import.meta.url), "utf8"));
const train = trains.find(item => item.id === "700t");
function storage() {
  const data = new Map();
  return { data, getItem: key => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key) };
}
function makeTrip({ level = "large", practice = "mixed", seed = 17, index = 0,
  challenge = false, recentQuestions = [], recentGames = [], journey = null, contentVersion = "1.8.0" } = {}) {
  const meta = { level, trainId: train.id, practice, challenge, seed, recentQuestions, recentGames, journey, contentVersion };
  const questions = createTrip({ level, train, trains, practice, challenge,
    rng: seededRandom(seed), recentQuestions, recentGames, journey, contentVersion });
  const q = questions[index];
  return { meta, train, questions, index, solved: false, assisted: true, awarded: false,
    attempts: 12, feedback: "PRIVATE FEEDBACK", boardingInput: "PRIVATE TYPED ANSWER",
    order: [], cargo: 0, memory: newMemoryState(), memoryPeek: false, counted: new Set(),
    ...newAdventureState(q), puzzle: q.game === "puzzle" ? newPuzzleState(q) : null,
    explorer: ["luggage", "maze"].includes(q.game) ? newExplorerState(q) : null,
    workshop: ["program", "balance"].includes(q.game) ? newWorkshopState(q) : null,
    discovery: ["mosaic", "differences"].includes(q.game) ? newDiscoveryState(q) : null,
    tickets: q.game === "tickets" ? newTicketsState(q) : null };
}
function partialWork(trip) {
  const q = trip.questions[trip.index];
  switch (q.game) {
    case "tickets": trip.tickets = payToken(q, trip.tickets, 0); break;
    case "program": {
      const direction = Object.keys(PROGRAM_DIRECTIONS).find(dir => !(q.walls[q.start] & PROGRAM_DIRECTIONS[dir].bit));
      trip.workshop = appendCommand(q, trip.workshop, direction);
      break;
    }
    case "balance": trip.workshop = addWeight(q, trip.workshop, q.allowedWeights[0]); break;
    case "mosaic": trip.discovery = paintMosaicCell(q, selectMosaicColor(q, trip.discovery, q.palette[1].id), 1); break;
    case "differences": trip.discovery = findDifference(q, trip.discovery, q.differences[0]); break;
    case "count": trip.counted = new Set(q.count >= 3 ? [2, 0] : q.count ? [0] : []); break;
    case "order": trip.order = [q.numbers[1], q.numbers[0]]; break;
    case "cargo": trip.cargo = Math.min(3, q.max); break;
    case "memory": {
      const id = q.pairs[0];
      trip.memory = { matched: q.deck.flatMap((value, index) => value === id ? [index] : []),
        open: [q.deck.findIndex(value => value !== id)], turns: 3 };
      trip.memoryPeek = true;
      break;
    }
    case "tracks": trip.rotations = trip.rotations.map(value => (value + 1) % 4); break;
    case "sharing": trip.shares[0] = Math.min(2, q.total); break;
    case "treasure": trip.found.add(q.items.findIndex(value => value === q.target)); break;
    case "puzzle":
      trip.puzzle = { placements: trip.puzzle.placements.map((_, index) => index === 1 ? q.pieces[0] : null),
        selectedPiece: q.pieces[1], moves: 2, preview: true };
      break;
    case "luggage":
      trip.explorer.luggageAssignments[0] = q.bins.find(bin => bin.id !== q.answer[0]).id;
      trip.explorer.luggageSelected = q.items.length - 1;
      break;
    case "maze": {
      const direction = Object.keys(MAZE_DIRECTIONS).find(key => !(q.walls[0] & MAZE_DIRECTIONS[key].bit));
      trip.explorer = moveMaze(q, trip.explorer, direction);
      break;
    }
  }
  return trip;
}
function snapshot(trip) {
  const target = storage();
  assert.equal(saveTripSession(target, trip), true);
  return JSON.parse(target.getItem(TRIP_SESSION_KEY));
}
function readSnapshot(value) {
  return readTripSession({ getItem: () => JSON.stringify(value) }, { trains });
}

test("recipes recreate the exact seeded mixed journey and history before restoring a station", () => {
  const previous = makeTrip({ seed: 4 });
  const recentQuestions = previous.questions.map(questionSignature);
  const recentGames = previous.questions.map(q => `${q.level}:${q.game}`);
  for (const level of Object.keys(LEVELS)) {
    for (let seed = 0; seed < 20; seed++) {
      const trip = makeTrip({ level, seed, challenge: seed % 2 === 0,
        recentQuestions, recentGames, index: seed % LEVELS[level].stops });
      const restored = readSnapshot(snapshot(trip));
      assert.ok(restored);
      assert.deepEqual(restored.questions, trip.questions, "answer order, layouts and targets must all be identical");
      assert.deepEqual(restored.meta, trip.meta);
      assert.equal(restored.index, trip.index);
      assert.equal(restored.train, train, "train details must come from the supplied catalogue");
    }
  }
});

test("all twenty activities preserve partial work and restore sets without saving private answers", () => {
  assert.equal(allowedGames("large").length, 20);
  for (const level of Object.keys(LEVELS)) {
    for (const practice of allowedGames(level)) {
      const trip = partialWork(makeTrip({ level, practice }));
      const saved = snapshot(trip), data = JSON.stringify(saved);
      assert.ok(!data.includes("PRIVATE"));
      assert.equal(saved.questions, undefined);
      assert.equal(saved.feedback, undefined);
      assert.equal(saved.boardingInput, undefined);
      const restored = readSnapshot(saved);
      assert.ok(restored, `${level}/${practice}`);
      assert.deepEqual(restored.questions, trip.questions);
      assert.equal(restored.attempts, 0);
      assert.equal(restored.boardingInput, "");
      assert.equal(restored.memoryPeek, false);
      assert.equal(restored.awarded, false);
      assert.equal(restored.assisted, true);
      assert.equal(restored.feedback, "");
      assert.ok(restored.counted instanceof Set && restored.found instanceof Set);
      for (const field of ["order", "cargo", "memory", "counted", "rotations", "shares", "found", "puzzle", "explorer", "workshop", "discovery", "tickets"])
        assert.deepEqual(restored[field], trip[field], `${level}/${practice}: ${field}`);
      const again = snapshot(restored);
      assert.deepEqual(again, saved, "saving an already restored trip cannot lose the current work");
    }
  }
});
test("v1.5 snapshots retain the original fifteen-game recipe and exact question content", () => {
  const fixtures = JSON.parse(readFileSync(new URL("./fixtures/trip-session-v1.5.json", import.meta.url), "utf8"));
  for (const fixture of fixtures) {
    const restored = readSnapshot(fixture.snapshot);
    assert.ok(restored);
    assert.deepEqual(restored.questions, fixture.expectedQuestions);
    assert.equal(restored.meta.contentVersion, "1.5.0");
    assert.equal(restored.meta.journey, null);
    const current = snapshot(restored);
    assert.equal(current.gameVersion, "1.8.0");
    assert.deepEqual(readSnapshot(current).questions, fixture.expectedQuestions);
  }
});
test("sparse commands or weights cannot overwrite a valid restorable snapshot", () => {
  for (const practice of ["program", "balance"]) {
    const trip = makeTrip({ practice });
    const target = storage();
    assert.equal(saveTripSession(target, trip), true);
    const valid = target.getItem(TRIP_SESSION_KEY);
    if (practice === "program") trip.workshop.commands = Array(1);
    else trip.workshop.weights = Array(1);
    assert.equal(saveTripSession(target, trip), false);
    assert.equal(target.getItem(TRIP_SESSION_KEY), valid);
    assert.ok(readTripSession(target, { trains }));
  }
});

test("the v1.8 release preserves all twelve captured v1.7 question recipes exactly", () => {
  const fixtures = JSON.parse(readFileSync(new URL("./fixtures/trip-session-v1.7.json", import.meta.url), "utf8"));
  assert.equal(fixtures.length, 12);
  for (const fixture of fixtures) {
    const restored = readSnapshot(fixture.snapshot);
    assert.ok(restored);
    assert.deepEqual(restored.questions, fixture.expectedQuestions);
    assert.equal(restored.meta.contentVersion, "1.7.0");
    const updated = snapshot(restored);
    assert.equal(updated.gameVersion, "1.8.0");
    assert.deepEqual(readSnapshot(updated).questions, fixture.expectedQuestions);
  }
});

test("v1.6 photo journeys resume their original illustrations after reference-photo metadata is added", () => {
  const originalTrains = trains.map(t => Object.fromEntries(Object.entries(t)
    .filter(([key]) => key !== "referencePhoto" && key !== "canonicalModel" && !key.startsWith("display"))));
  for (const level of Object.keys(LEVELS)) for (const practice of ["identify", "memory", "puzzle", "mixed"]) {
    const trip = partialWork(makeTrip({ level, practice, seed: 1606, contentVersion: "1.6.0" }));
    const old = snapshot(trip); old.gameVersion = "1.6.0";
    const expected = createTrip({ level, practice, train: originalTrains.find(t => t.id === train.id),
      trains: originalTrains, rng: seededRandom(1606), contentVersion: "1.6.0" });
    const restored = readSnapshot(old);
    assert.ok(restored);
    assert.deepEqual(restored.questions, expected);
    assert.equal(restored.meta.contentVersion, "1.6.0");
    assert.deepEqual(snapshot(restored).work, old.work);
    if (practice === "puzzle") assert.equal(restored.questions[0].image,
      originalTrains.find(t => t.id === restored.questions[0].target).image);
  }
});
test("themed recipes restore the same route and work without adopting stored story text", () => {
  for (const journey of ["forest", "coast", "freight", "engineer", "picnic", "depot"]) {
    for (const level of Object.keys(LEVELS)) {
      const trip = partialWork(makeTrip({ level, journey }));
      const restored = readSnapshot(snapshot(trip));
      assert.equal(restored.meta.journey, journey);
      assert.deepEqual(restored.questions, trip.questions);
    }
  }
  const valid = snapshot(makeTrip());
  valid.meta.journey = "made-up";
  assert.equal(readSnapshot(valid), null);
});

test("privacy fields are never read, even when a solved arithmetic question is suspended", () => {
  const trip = makeTrip({ practice: "boarding" });
  trip.solved = true;
  for (const field of ["feedback", "boardingInput", "attempts"])
    Object.defineProperty(trip, field, { get() { assert.fail(`save must not read ${field}`); } });
  const saved = snapshot(trip), restored = readSnapshot(saved);
  assert.equal(restored.solved, true);
  assert.ok(restored.feedback.includes("完成"));
  assert.equal(restored.boardingInput, "");
  assert.equal(restored.attempts, 0);
});

test("invalid versions, recipe data, station flags and injected question fields are rejected", () => {
  const valid = snapshot(makeTrip());
  const mutations = [
    value => { value.version = 2; }, value => { value.gameVersion = "1.4.0"; },
    value => { value.awarded = true; }, value => { value.solved = "true"; },
    value => { value.assisted = 1; }, value => { value.index = -1; },
    value => { value.index = 5; }, value => { value.index = 0.5; },
    value => { value.meta.level = "constructor"; }, value => { value.meta.trainId = "unknown"; },
    value => { value.meta.practice = "unknown"; }, value => { value.meta.challenge = "false"; },
    value => { value.meta.seed = -1; }, value => { value.meta.seed = 0x100000000; },
    value => { value.meta.seed = 1.5; }, value => { value.meta.seed = "17"; },
    value => { value.meta.recentQuestions = Array(97).fill("[]"); },
    value => { value.meta.recentQuestions = ["x".repeat(1025)]; },
    value => { value.meta.recentGames = Array(49).fill("large:count"); },
    value => { value.meta.recentGames = ["x".repeat(65)]; },
    value => { value.meta.recentQuestions = [null]; },
    value => { value.questions = [{ prompt: '<img src=x onerror="alert(1)">' }]; },
    value => { value.work.feedback = "<script>evil()</script>"; },
    value => { value.meta.prompt = "a supplied question"; },
    value => { delete value.work; },
  ];
  for (const mutate of mutations) {
    const invalid = structuredClone(valid);
    mutate(invalid);
    assert.equal(readSnapshot(invalid), null);
  }
  const boundedHistory = structuredClone(valid);
  boundedHistory.meta.recentQuestions = ['<img src=x onerror="alert(1)">', '["large","count","<script>evil()</script>"]'];
  boundedHistory.meta.recentGames = ["<script>evil()</script>"];
  const restored = readSnapshot(boundedHistory);
  assert.ok(restored, "bounded history strings are filtered by the engine rather than used as question text");
  assert.ok(!JSON.stringify(restored.questions).includes("<img") && !JSON.stringify(restored.questions).includes("<script"));
  assert.equal(readTripSession({ getItem: () => JSON.stringify(valid) }, { trains: [] }), null);
});

test("work validation rejects out-of-range, duplicated and contradictory state instead of silently losing it", () => {
  const cases = [
    ["count", work => { work.counted = [-1]; }], ["count", work => { work.counted = [0, 0]; }],
    ["order", work => { work.order = [999]; }], ["order", work => { work.order = [work.order[0], work.order[0]]; }],
    ["cargo", work => { work.cargo = 21; }], ["cargo", work => { work.cargo = 1.5; }],
    ["memory", work => { work.memory.open = [0, 1, 2]; }],
    ["memory", work => { work.memory.matched = [0]; }],
    ["memory", work => { work.memory.open = [work.memory.matched[0]]; }],
    ["memory", work => { work.memory.turns = -1; }],
    ["tracks", work => { work.rotations[0] = 4; }], ["tracks", work => { work.rotations = []; }],
    ["sharing", work => { work.shares = work.shares.map(() => 20); }],
    ["sharing", work => { work.shares[0] = -1; }],
    ["treasure", work => { work.found = [-1]; }],
    ["treasure", (work, q) => { work.found = [q.items.findIndex(item => item !== q.target)]; }],
    ["puzzle", work => { work.puzzle.placements[0] = work.puzzle.placements[1]; }],
    ["puzzle", work => { work.puzzle.selectedPiece = 9; }],
    ["puzzle", work => { work.puzzle.moves = -1; }], ["puzzle", work => { work.puzzle.preview = "yes"; }],
    ["luggage", work => { work.luggageAssignments[0] = "<img>"; }],
    ["luggage", work => { work.luggageSelected = 99; }],
    ["luggage", work => { work.luggageSelected = 0; }],
    ["maze", work => { work.mazePosition = 25; }],
    ["maze", work => { work.mazeVisited = [0]; }],
    ["maze", work => { work.mazeVisited.push(work.mazeVisited[0]); }],
    ["maze", work => { work.mazeMoves = -1; }],
  ];
  for (const [practice, mutate] of cases) {
    const trip = partialWork(makeTrip({ practice }));
    const invalid = snapshot(trip);
    mutate(invalid.work, trip.questions[trip.index]);
    assert.equal(readSnapshot(invalid), null, practice);
  }
  for (const [practice, field] of [["memory", "turns"], ["puzzle", "moves"], ["maze", "mazeMoves"]]) {
    const valid = snapshot(partialWork(makeTrip({ practice })));
    const target = practice === "memory" ? valid.work.memory : practice === "puzzle" ? valid.work.puzzle : valid.work;
    target[field] = Number.MAX_SAFE_INTEGER;
    assert.ok(readSnapshot(valid), "finite safe integer counters are accepted");
    target[field] = Number.MAX_SAFE_INTEGER + 1;
    assert.equal(readSnapshot(valid), null, "unsafe integer counters are rejected");
  }
});

test("completed activity snapshots require matching work and cannot skip an unfinished station", () => {
  for (const practice of ["order", "cargo", "memory", "tracks", "sharing", "treasure", "puzzle", "luggage", "maze"]) {
    const trip = partialWork(makeTrip({ practice }));
    const q = trip.questions[0], raw = snapshot(trip);
    if (practice === "cargo") raw.work.cargo = (q.answer + 1) % (q.max + 1);
    if (practice === "tracks") raw.work.rotations[q.start] = (q.tiles[q.start].solution + 1) % 4;
    raw.solved = true;
    assert.equal(readSnapshot(raw), null, `${practice}: partial work cannot become a completed station`);
    trip.solved = true;
    if (practice === "cargo") trip.cargo = raw.work.cargo;
    if (practice === "tracks") trip.rotations = raw.work.rotations;
    const target = storage(); target.setItem(TRIP_SESSION_KEY, "prior safe snapshot");
    assert.equal(saveTripSession(target, trip), false, practice);
    assert.equal(target.getItem(TRIP_SESSION_KEY), "prior safe snapshot");
  }
  for (const practice of ["order", "cargo", "memory", "tracks", "sharing", "treasure", "puzzle", "luggage"]) {
    const trip = makeTrip({ practice }), q = trip.questions[0];
    if (practice === "order") trip.order = [...q.answer];
    if (practice === "cargo") trip.cargo = q.answer;
    if (practice === "memory") trip.memory = { open: [], matched: q.deck.map((_, i) => i), turns: q.pairs.length };
    if (practice === "tracks") trip.rotations = q.tiles.map(t => t.solution);
    if (practice === "sharing") trip.shares = [...q.answer];
    if (practice === "treasure") trip.found = new Set(q.items.flatMap((item, i) => item === q.target ? [i] : []));
    if (practice === "puzzle") trip.puzzle = { placements: [...q.answer], selectedPiece: null, moves: q.answer.length, preview: false };
    if (practice === "luggage") { trip.explorer.luggageAssignments = [...q.answer]; trip.explorer.luggageSelected = null; }
    trip.solved = true;
    assert.ok(readSnapshot(snapshot(trip)), `${practice}: a real completed station still resumes`);
  }
});

test("missing, truncated, oversized or private storage never throws and does not touch the passport", () => {
  const target = storage(), trip = makeTrip();
  target.setItem("taiwan-train-math.v1", "PRIVATE PASSPORT");
  assert.equal(readTripSession(target, { trains }), null);
  for (const data of ["", "{truncated", "null", "[]", " ".repeat(131073)]) {
    target.setItem(TRIP_SESSION_KEY, data);
    assert.equal(readTripSession(target, { trains }), null);
  }
  assert.equal(saveTripSession(target, trip), true);
  assert.equal(clearTripSession(target), true);
  assert.equal(target.getItem(TRIP_SESSION_KEY), null);
  assert.equal(target.getItem("taiwan-train-math.v1"), "PRIVATE PASSPORT");
  const blocked = { getItem() { throw new Error("private mode"); },
    setItem() { throw new Error("private mode"); }, removeItem() { throw new Error("private mode"); } };
  assert.equal(saveTripSession(blocked, trip), false);
  assert.equal(readTripSession(blocked, { trains }), null);
  assert.equal(clearTripSession(blocked), false);
  assert.equal(saveTripSession(target, { ...trip, awarded: true }), false);
  assert.equal(saveTripSession(target, { ...trip, meta: { ...trip.meta, trainId: "unknown" } }), false);
  assert.equal(saveTripSession(target, { ...trip, index: -1 }), false);
  for (const seed of [0, 0xffffffff]) assert.ok(readSnapshot(snapshot(makeTrip({ seed }))));
});

test("ticket work rejects sparse, impossible and completed-but-unpaid states without losing a valid save", () => {
  const trip = partialWork(makeTrip({ practice: "tickets" })), raw = snapshot(trip);
  for (const mutate of [
    s => { s.work.activeTicket = 3; }, s => { s.work.assignments[0] = 3; },
    s => { s.work.assignments[0] = "PRIVATE ANSWER"; }, s => { s.work.checked = "yes"; },
    s => { s.work.assignments.pop(); }, s => { s.solved = true; },
    s => { s.work.checked = true; s.solved = true; },
    s => { s.meta.contentVersion = "1.7.0"; },
  ]) {
    const bad = structuredClone(raw); mutate(bad); assert.equal(readSnapshot(bad), null);
  }
  const target = storage(); assert.equal(saveTripSession(target, trip), true);
  const valid = target.getItem(TRIP_SESSION_KEY);
  trip.tickets.assignments = Array(trip.questions[0].wallet.length);
  assert.equal(saveTripSession(target, trip), false);
  assert.equal(target.getItem(TRIP_SESSION_KEY), valid);
});
