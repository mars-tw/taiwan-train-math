import test from "node:test";
import assert from "node:assert/strict";
import { defaults } from "../src/engine.js";
import { encodeBackup, decodeBackup } from "../src/progress-backup.js";
import { readFileSync } from "node:fs";
const { trains } = JSON.parse(readFileSync(new URL("../data/trains.json", import.meta.url), "utf8"));
test("passport backup restores collection and settings while omitting arbitrary private fields", () => {
  const progress = { ...defaults(), trips: 4, completed: ["700t"], souvenirs: ["star-letter"], childName: "PRIVATE", input: "PRIVATE", email: "PRIVATE" };
  const encoded = encodeBackup(progress);
  assert.doesNotMatch(encoded, /PRIVATE|childName|email|input/);
  const restored = decodeBackup(encoded);
  assert.equal(restored.progress.trips, 4); assert.deepEqual(restored.progress.completed, ["700t"]);
  assert.deepEqual(restored.progress.souvenirs, ["star-letter"]); assert.equal(restored.trip, null);
});
test("only validated legacy journeys are included in an exported backup and restore the same work", () => {
  const fixture = JSON.parse(readFileSync(new URL("./fixtures/trip-session-v1.7.json", import.meta.url), "utf8"))[0];
  const session = JSON.stringify(fixture.snapshot);
  const decoded = decodeBackup(encodeBackup(defaults(), session, { trains }), { trains });
  assert.deepEqual(decoded.trip.questions, fixture.expectedQuestions);
  assert.deepEqual(JSON.parse(decoded.session).work, fixture.snapshot.work);
  assert.equal(JSON.parse(encodeBackup(defaults(), '{"childName":"PRIVATE"}', { trains })).session, null);
});
test("wrong app, unsupported version and injected trip cannot silently replace progress", () => {
  for (const text of ["", "{}", '{"format":"other"}', "x".repeat(262145), JSON.stringify({ format: "taiwan-train-math.backup", version: 1, passport: defaults(), session: '{"questions":[{"answer":5}]}' })]) assert.throws(() => decodeBackup(text));
});
