export function createProgramPlayback({ schedule = setTimeout, cancel = clearTimeout, delay = 420 } = {}) {
  let active = null;
  function stop() {
    if (active?.timer !== undefined) cancel(active.timer);
    active = null;
  }
  return {
    stop,
    start(result, { onStep, onDone }) {
      stop();
      if (!Array.isArray(result?.trace) || result.trace.length < 1 || result.trace.length > 64
        || Array.from(result.trace).some(position => !Number.isInteger(position) || position < 0)
        || result.position !== result.trace.at(-1) || typeof onStep !== "function" || typeof onDone !== "function")
        throw new Error("Invalid program playback");
      const run = { timer: undefined, index: 0, trace: [...result.trace] };
      active = run;
      function step() {
        if (active !== run) return;
        if (run.index >= run.trace.length) { active = null; onDone(result); return; }
        onStep({ position: run.trace[run.index], trace: run.trace.slice(0, run.index + 1), index: run.index });
        run.index++;
        if (active !== run) return;
        if (run.index === run.trace.length) { active = null; onDone(result); return; }
        run.timer = schedule(step, typeof delay === "function" ? delay() : delay);
      }
      step();
    },
  };
}
