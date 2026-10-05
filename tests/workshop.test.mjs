import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  PROGRAM_DIRECTIONS, createProgramQuestion, createBalanceQuestion, newWorkshopState, resetWorkshopState,
  appendCommand, removeCommand, evaluateProgram, addWeight, removeWeight, weightTotal, workshopScene,
} from "../src/workshop.js";
const levels = ["small", "medium", "large"];
function random(seed) {
  let value = seed >>> 0;
  return () => { value = (Math.imul(value, 1664525) + 1013904223) >>> 0; return value / 4294967296; };
}
function programPath(q) {
  const queue = [{ position: q.start, commands: [] }], visited = new Set([q.start]);
  for (let at = 0; at < queue.length; at++) {
    const current = queue[at];
    if (current.position === q.finish) return current.commands;
    const x = current.position % q.columns, y = Math.floor(current.position / q.columns);
    for (const [name, direction] of Object.entries(PROGRAM_DIRECTIONS)) {
      const nx = x + direction.dx, ny = y + direction.dy;
      if (nx < 0 || nx >= q.columns || ny < 0 || ny >= q.rows) continue;
      const next = ny * q.columns + nx;
      if (!(q.walls[current.position] & direction.bit) && !(q.walls[next] & direction.opposite) && !visited.has(next)) {
        visited.add(next); queue.push({ position: next, commands: [...current.commands, name] });
      }
    }
  }
  return null;
}
function balanceCoins(q) {
  const queue = [{ total: 0, weights: [] }], visited = new Set([0]);
  for (let at = 0; at < queue.length; at++) {
    const current = queue[at];
    if (current.total === q.target) return current.weights;
    if (current.weights.length === q.maxBoxes) continue;
    for (const value of q.allowedWeights) {
      const next = current.total + value;
      if (next <= q.target && !visited.has(next)) {
        visited.add(next); queue.push({ total: next, weights: [...current.weights, value] });
      }
    }
  }
  return null;
}
test("all program grids have a bounded age-appropriate route and symmetric walls", () => {
  for (const level of levels) {
    const seen = new Set();
    for (let seed = 0; seed < 500; seed++) {
      const q = createProgramQuestion({ level, rng: random(Math.imul(seed + 1, 2654435761)) });
      const size = { small: 3, medium: 4, large: 5 }[level];
      assert.equal(q.columns, size); assert.equal(q.rows, size);
      assert.equal(q.maxCommands, { small: 6, medium: 10, large: 16 }[level]);
      assert.equal(q.walls.length, size * size);
      const path = programPath(q);
      assert.ok(path && path.length <= q.maxCommands, `${level}, seed ${seed}`);
      const evaluation = evaluateProgram(q, path);
      assert.equal(evaluation.arrived, true); assert.equal(evaluation.blocked, false);
      assert.equal(evaluation.position, q.finish);
      assert.equal(evaluation.trace.length, path.length + 1);
      for (let position = 0; position < q.walls.length; position++) {
        const x = position % size, y = Math.floor(position / size);
        assert.ok(q.walls[position] >= 0 && q.walls[position] <= 15);
        if (x === 0) assert.ok(q.walls[position] & 8);
        if (y === 0) assert.ok(q.walls[position] & 1);
        if (x === size - 1) assert.ok(q.walls[position] & 2);
        if (y === size - 1) assert.ok(q.walls[position] & 4);
        if (x < size - 1) assert.equal(Boolean(q.walls[position] & 2), Boolean(q.walls[position + 1] & 8));
        if (y < size - 1) assert.equal(Boolean(q.walls[position] & 4), Boolean(q.walls[position + size] & 1));
      }
      assert.ok(!Object.hasOwn(q, "solution") && !Object.hasOwn(q, "path"));
      assert.doesNotMatch(q.hint, /\d|先往|再往|下一步/);
      seen.add(JSON.stringify(q.walls));
    }
    assert.ok(seen.size > 30, `${level}: routes vary across seeded journeys`);
  }
});
test("constant and extreme randomness cannot cause infinite program retries", () => {
  for (const value of [0, 1, NaN]) for (const level of levels) {
    let calls = 0;
    const q = createProgramQuestion({ level, rng: () => { calls++; return value; } });
    assert.ok(programPath(q).length <= q.maxCommands);
    assert.ok(calls <= 8 * (q.walls.length - 1) + 2 * (q.columns - 1) + 2);
  }
  assert.throws(() => createProgramQuestion({ level: "unknown" }));
});
test("planning and editing do not move the train; edits clear only the previous execution", () => {
  const q = createProgramQuestion({ level: "small", rng: random(8) });
  const initial = newWorkshopState(q);
  Object.freeze(initial.commands); Object.freeze(initial.programTrace); Object.freeze(initial);
  const planned = appendCommand(q, initial, "right");
  assert.deepEqual(initial.commands, []); assert.deepEqual(planned.commands, ["right"]);
  assert.equal(planned.programPosition, q.start); assert.deepEqual(planned.programTrace, [q.start]);
  const commands = programPath(q), result = evaluateProgram(q, commands);
  const ran = { ...initial, commands, programPosition: result.position, programTrace: result.trace, programChecked: true };
  const edited = removeCommand(q, ran, 0);
  assert.equal(edited.programChecked, false); assert.equal(edited.programPosition, q.start);
  assert.deepEqual(edited.programTrace, [q.start]);
  assert.deepEqual(edited.commands, commands.slice(1));
  assert.equal(ran.programPosition, q.finish);
  assert.deepEqual(removeCommand(q, planned).commands, []);
  assert.deepEqual(removeCommand(q, ran, null).commands, []);
  assert.deepEqual(resetWorkshopState(q), newWorkshopState(q));
  let full = initial;
  for (let i = 0; i < q.maxCommands; i++) full = appendCommand(q, full, "right");
  assert.equal(appendCommand(q, full, "down"), full);
  for (const direction of ["bad", "__proto__", "constructor", 1, {}, null, new String("up")])
    assert.equal(appendCommand(q, initial, direction), initial);
  for (const index of [-1, 1, 0.5, "0", NaN]) assert.equal(removeCommand(q, planned, index), planned);
  assert.equal(removeCommand(q, initial), initial);
  assert.equal(appendCommand(q, { ...initial, commands: ["bad"] }, "right").commands[0], "bad");
});
test("execution stops at a wall, never exits the board, and requires the final position to arrive", () => {
  const q = createProgramQuestion({ level: "small", rng: random(10) });
  assert.deepEqual(evaluateProgram(q, ["up", "right"]), { arrived: false, position: q.start, trace: [q.start], blocked: true });
  const borderless = { ...q, walls: [...q.walls] }; borderless.walls[0] = 0;
  assert.equal(evaluateProgram(borderless, ["up"]).position, 0);
  assert.equal(evaluateProgram(borderless, ["up"]).blocked, true);
  const inconsistent = { ...q, walls: Array(q.walls.length).fill(15) }; inconsistent.walls[0] &= ~2;
  assert.equal(evaluateProgram(inconsistent, ["right"]).blocked, true);
  const path = programPath(q), last = PROGRAM_DIRECTIONS[path.at(-1)];
  const opposite = Object.entries(PROGRAM_DIRECTIONS).find(([, direction]) => direction.bit === last.opposite)[0];
  const leaving = evaluateProgram(q, [...path, opposite]);
  assert.equal(leaving.arrived, false); assert.notEqual(leaving.position, q.finish);
  for (const commands of [null, "right", ["wrong"], Array(q.maxCommands + 1).fill("right")]) {
    const result = evaluateProgram(q, commands);
    assert.equal(result.arrived, false); assert.equal(result.blocked, true); assert.deepEqual(result.trace, [q.start]);
  }
});
test("every balance target is reachable with the age's finite labelled boxes", () => {
  for (const level of levels) {
    const seen = new Set();
    for (let seed = 0; seed < 500; seed++) {
      const q = createBalanceQuestion({ level, rng: random(Math.imul(seed + 1, 2654435761)) });
      assert.deepEqual(q.allowedWeights, { small: [1, 2], medium: [1, 2, 5], large: [2, 3, 5] }[level]);
      assert.ok(q.target >= 1 && q.target <= { small: 5, medium: 10, large: 20 }[level]);
      assert.ok(q.maxBoxes <= (level === "small" ? 6 : 8));
      const weights = balanceCoins(q);
      assert.ok(weights && weights.length <= q.maxBoxes);
      assert.equal(weightTotal(q, weights), q.target); assert.equal(q.answer, q.target);
      if (level === "large") assert.notEqual(q.target, 1);
      assert.doesNotMatch(q.hint, /\d|缺|還差|需要再/);
      seen.add(q.target);
    }
    assert.equal(seen.size, { small: 5, medium: 10, large: 19 }[level]);
  }
  assert.throws(() => createBalanceQuestion({ level: "unknown" }));
});
test("balance allows experimentation, preserves previous work and clears outdated check results", () => {
  const q = createBalanceQuestion({ level: "large", rng: random(22) }), initial = newWorkshopState(q);
  Object.freeze(initial.weights); Object.freeze(initial);
  const added = addWeight(q, initial, 5);
  assert.deepEqual(initial.weights, []); assert.deepEqual(added.weights, [5]);
  const checked = { ...added, balanceChecked: true, balanceTilt: -1 };
  const adjusted = addWeight(q, checked, 2);
  assert.deepEqual(adjusted.weights, [5, 2]); assert.equal(adjusted.balanceChecked, false); assert.equal(adjusted.balanceTilt, 0);
  const removed = removeWeight(q, checked, 0);
  assert.deepEqual(removed.weights, []); assert.equal(removed.balanceChecked, false); assert.equal(checked.balanceChecked, true);
  let full = initial;
  for (let i = 0; i < q.maxBoxes; i++) full = addWeight(q, full, 5);
  assert.equal(weightTotal(q, full.weights), 40, "an overweight attempt stays legal without displaying its total or rejecting a clue");
  assert.equal(addWeight(q, full, 2), full);
  for (const value of [1, 0, -2, 4, "2", null, {}, NaN]) assert.equal(addWeight(q, initial, value), initial);
  for (const index of [-1, 1, "0", 0.5, null]) assert.equal(removeWeight(q, added, index), added);
  for (const weights of [null, {}, [1], ["2"], Array(9).fill(2)]) assert.equal(weightTotal(q, weights), null);
  assert.equal(weightTotal(q, []), 0);
  assert.equal(weightTotal({ ...q, target: 1 }, []), null);
  assert.equal(weightTotal({ ...q, level: "__proto__" }, []), null);
  assert.equal(addWeight(q, { ...initial, balanceTilt: 7 }, 2).weights.length, 0);
  assert.deepEqual(resetWorkshopState(q), initial);
});
test("program markup never reads a solution or previews the child's unexecuted commands", () => {
  const q = createProgramQuestion({ level: "medium", rng: random(32) });
  for (const key of ["answer", "solution", "path"]) Object.defineProperty(q, key, { get() { assert.fail(`UI must not read ${key}`); } });
  let state = appendCommand(q, newWorkshopState(q), "right");
  const before = workshopScene(q, { workshop: state });
  assert.equal((before.match(/class="program-train"/g) || []).length, 1);
  assert.match(before, /data-program-cell="0"[^>]*><span class="program-train"/);
  assert.doesNotMatch(before, /program-visited|data-answer=|solution|correct-path/);
  assert.equal((before.match(/data-program-direction=/g) || []).length, 4);
  assert.match(before, /data-program-remove="0"/); assert.match(before, /id="program-run"/); assert.match(before, /id="program-reset"/);
  const route = programPath(q).slice(0, 2), result = evaluateProgram(q, route);
  state = { ...state, commands: route, programChecked: true, programPosition: result.position, programTrace: result.trace };
  const after = workshopScene(q, { workshop: state });
  assert.equal((after.match(/program-visited/g) || []).length, new Set(result.trace).size);
  const empty = workshopScene(q, { workshop: newWorkshopState(q) });
  assert.match(empty, /id="program-run"[^>]*disabled/);
});
test("balance remains neutral before checking and never shows a wrong or pending total", () => {
  const q = { ...createBalanceQuestion({ level: "medium", rng: random(37) }), target: 7 };
  Object.defineProperty(q, "answer", { get() { assert.fail("the illustration must not read the answer"); } });
  let state = addWeight(q, newWorkshopState(q), 5);
  state = addWeight(q, state, 5);
  const pending = workshopScene(q, { workshop: { ...state, balanceTilt: -1 } });
  assert.match(pending, /待檢查，先保持水平/);
  assert.doesNotMatch(pending, /總共|10 公斤|缺|還差|比較重|比較輕/);
  assert.match(pending, /data-balance-weight="1"/); assert.match(pending, /data-balance-remove="0"/);
  assert.match(pending, /id="balance-check"/); assert.match(pending, /id="balance-reset"/);
  const heavy = workshopScene(q, { workshop: { ...state, balanceChecked: true, balanceTilt: -1 } });
  assert.match(heavy, /你放的這一邊比較重/); assert.doesNotMatch(heavy, /總共|10 公斤|缺|還差/);
  const light = workshopScene(q, { workshop: { ...state, balanceChecked: true, balanceTilt: 1 } });
  assert.match(light, /你放的這一邊比較輕/); assert.doesNotMatch(light, /總共|10 公斤|缺|還差/);
  const correct = workshopScene(q, { workshop: { ...state, weights: [5, 2], balanceChecked: true, balanceTilt: 0 }, solved: true });
  assert.match(correct, /總共 7 公斤，剛好一樣重/);
  assert.match(correct, /id="balance-check"[^>]*disabled/);
});
test("workshop controls are keyboard buttons with bounded responsive containers", () => {
  for (const game of ["program", "balance"]) {
    const q = game === "program" ? createProgramQuestion({ level: "small" }) : createBalanceQuestion({ level: "small" });
    const markup = workshopScene(q, { workshop: newWorkshopState(q) });
    assert.ok([...markup.matchAll(/<button\b[^>]*>/g)].every(match => match[0].includes('type="button"')));
    assert.doesNotMatch(markup, /autofocus|onfocus=|onclick=|setTimeout/);
  }
  const css = readFileSync(new URL("../src/workshop.css", import.meta.url), "utf8");
  assert.match(css, /min-width: 48px/); assert.match(css, /min-height: 48px/);
  assert.match(css, /minmax\(0, 1fr\)/); assert.match(css, /overflow-x: auto/);
  assert.match(css, /:focus-visible/); assert.match(css, /orientation: landscape/);
  assert.equal(workshopScene(null, {}), ""); assert.equal(workshopScene({ game: "unknown" }, {}), "");
});
