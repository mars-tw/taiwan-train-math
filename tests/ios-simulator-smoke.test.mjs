import assert from "node:assert/strict";
import { test } from "node:test";
import { visibleNativeFrame, waitForVisibleNativeFrame } from "../scripts/ios-simulator-smoke.mjs";

const stats = (stdev, entropy) => ({ channels: stdev.map(value => ({ stdev: value })), entropy });

test("the observed iPad cold-launch background and launch splash cannot count as gameplay", () => {
  // Run 38334544182: the first iPad frame was #f8f6f0, but its relaunch showed the home screen.
  assert.equal(visibleNativeFrame(stats([4.63, 4.28, 4.36], 0.01)), false);
  assert.equal(visibleNativeFrame(stats([29.23, 26.22, 26.03], 0.18)), false);
  assert.equal(visibleNativeFrame(stats([97.16, 87.02, 89.09], 5.51)), true);
  assert.equal(visibleNativeFrame(stats([93.69, 80.94, 82.05], 5.45)), true);
});

test("cold-launch capture waits for a visible frame and retains every observation", async () => {
  const delays = [];
  const result = await waitForVisibleNativeFrame({
    capture: async index => `frame-${index}.png`,
    inspect: async path => ({ width: 2064, height: 2752,
      stats: path === "frame-1.png" ? stats([4.63, 4.28, 4.36], 0.01)
        : stats([97.16, 87.02, 89.09], 5.51) }),
    pause: async milliseconds => { delays.push(milliseconds); },
    initialDelayMs: 30000, retryDelayMs: 5000, maxObservations: 3,
  });
  assert.equal(result.path, "frame-2.png");
  assert.deepEqual(result.observations.map(item => item.visible), [false, true]);
  assert.deepEqual(delays, [30000, 5000]);
});

test("persistent splash fails the cold-launch gate instead of proceeding to relaunch", async () => {
  let captures = 0;
  const delays = [];
  await assert.rejects(waitForVisibleNativeFrame({
    capture: async () => `frame-${++captures}.png`,
    inspect: async () => ({ width: 2064, height: 2752, stats: stats([4.63, 4.28, 4.36], 0.01) }),
    pause: async milliseconds => { delays.push(milliseconds); },
    initialDelayMs: 30000, retryDelayMs: 5000, maxObservations: 3,
  }), /stayed on a blank\/splash frame through 3 captures/);
  assert.equal(captures, 3);
  assert.deepEqual(delays, [30000, 5000, 5000]);
});
