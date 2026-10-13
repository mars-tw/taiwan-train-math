import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const target = join(root, "output/native-artifacts/ios");
const appPath = join(root, "output/ios-derived/Build/Products/Debug-iphonesimulator/App.app");
const preparationName = "prepared-simulators.json";
const appId = "tw.mars.trainmath";
const coldFrameInitialDelayMs = 30000;
const coldFrameRetryDelayMs = 5000;
const coldFrameMaxObservations = 13; // Observe at 30–90 seconds, then fail instead of accepting a splash.
const uuid = value => typeof value === "string" && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(value);
const typeId = value => typeof value === "string" && /^com\.apple\.CoreSimulator\.SimDeviceType\.[a-zA-Z0-9.-]+$/.test(value);
const runSimctl = (args, { timeout = 180000 } = {}) => execFileSync("xcrun", ["simctl", ...args], {
  encoding: "utf8", timeout, maxBuffer: 8 * 1024 * 1024,
});
const versionParts = runtime => String(runtime.version || runtime.identifier?.split("iOS-")[1]?.replaceAll("-", ".") || "")
  .split(".").map(part => Number(part));
function compareVersion(a, b) {
  const left = versionParts(a), right = versionParts(b);
  for (let index = 0; index < Math.max(left.length, right.length); index++) {
    const difference = (right[index] || 0) - (left[index] || 0);
    if (difference) return difference;
  }
  return 0;
}
const modelOrder = new Intl.Collator("en", { numeric: true });

export function selectSimulatorPlan(inventory) {
  const runtimes = (inventory?.runtimes || []).filter(runtime => runtime.isAvailable === true
    && !runtime.availabilityError && /^com\.apple\.CoreSimulator\.SimRuntime\.iOS-\d+(?:-\d+)*$/.test(runtime.identifier)
    && versionParts(runtime).every(Number.isFinite)).sort(compareVersion);
  const catalog = new Map((inventory?.devicetypes || []).filter(type => typeId(type.identifier)).map(type => [type.identifier, type]));
  for (const runtime of runtimes) {
    // Reuse a compatible model identifier, never the preinstalled device's data.
    const existing = (inventory.devices?.[runtime.identifier] || []).filter(device => device.isAvailable === true && typeId(device.deviceTypeIdentifier))
      .map(device => ({ identifier: device.deviceTypeIdentifier, name: catalog.get(device.deviceTypeIdentifier)?.name || device.name }));
    const [major = 0, minor = 0, patch = 0] = versionParts(runtime);
    const runtimeNumber = major * 65536 + minor * 256 + patch;
    const compatible = [...catalog.values()].filter(type =>
      (type.minRuntimeVersion === undefined || runtimeNumber >= type.minRuntimeVersion)
      && (type.maxRuntimeVersion === undefined || runtimeNumber <= type.maxRuntimeVersion));
    const choose = predicate => {
      const proven = existing.filter(type => predicate(type.name));
      return (proven.length ? proven : compatible.filter(type => predicate(type.name)))
        .sort((a, b) => modelOrder.compare(b.name, a.name))[0];
    };
    const iphone = choose(name => /^iPhone\b/.test(name) && /Pro Max\b/.test(name));
    const ipad = choose(name => /^iPad Pro\b/.test(name) && /13-inch\b/.test(name));
    if (iphone && ipad) return {
      runtime: { identifier: runtime.identifier, name: runtime.name, version: runtime.version },
      models: [{ kind: "iphone", ...iphone }, { kind: "ipad", ...ipad }],
    };
  }
  throw new Error("An available iOS runtime with iPhone Pro Max and 13-inch iPad Pro device types is required");
}

async function inventoryFrom(run) { return JSON.parse(await run(["list", "--json"])); }
function summary(error) { return String(error?.message || error).slice(0, 2000); }
export function visibleNativeFrame(stats) {
  const rgb = stats?.channels?.slice(0, 3).map(channel => channel.stdev);
  return rgb?.length === 3 && rgb.every(value => Number.isFinite(value) && value >= 20)
    && Number.isFinite(stats.entropy) && stats.entropy >= 2;
}

export async function waitForVisibleNativeFrame({ capture, inspect, pause,
  initialDelayMs = coldFrameInitialDelayMs, retryDelayMs = coldFrameRetryDelayMs,
  maxObservations = coldFrameMaxObservations, onObservation = () => {} } = {}) {
  if (typeof capture !== "function" || typeof inspect !== "function" || typeof pause !== "function"
    || typeof onObservation !== "function" || !Number.isSafeInteger(maxObservations) || maxObservations < 1
    || !Number.isSafeInteger(initialDelayMs) || initialDelayMs < 0
    || !Number.isSafeInteger(retryDelayMs) || retryDelayMs < 0)
    throw new Error("Invalid native frame observation plan");
  const observations = [];
  await pause(initialDelayMs);
  for (let index = 1; index <= maxObservations; index++) {
    const path = await capture(index);
    const { width, height, stats } = await inspect(path);
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1)
      throw new Error("Simulator screenshot dimensions are unavailable");
    const meanRgbStdev = stats?.channels?.slice(0, 3).reduce((sum, channel) => sum + channel.stdev, 0) / 3;
    const observation = { index, observedAtUtc: new Date().toISOString(), width, height, entropy: stats?.entropy,
      meanRgbStdev: Number.isFinite(meanRgbStdev) ? meanRgbStdev : null,
      visible: visibleNativeFrame(stats) };
    observations.push(observation);
    onObservation(observation);
    if (observation.visible) return { path, width, height, observations };
    if (index < maxObservations) await pause(retryDelayMs);
  }
  const last = observations.at(-1);
  const error = new Error(`Native cold launch stayed on a blank/splash frame through ${maxObservations} captures (${initialDelayMs + retryDelayMs * (maxObservations - 1)} ms planned wait; last entropy ${last?.entropy}, RGB deviation ${last?.meanRgbStdev})`);
  error.observations = observations;
  throw error;
}
async function boot(run, udid) {
  try { await run(["boot", udid]); }
  catch (error) { if (!String(error.stderr).includes("current state: Booted")) throw error; }
}

export async function prepareSimulators({ run = runSimctl, output = target, write = writeFile, ensureDirectory = mkdir,
  tag = `TrainMath-CI-${process.env.GITHUB_RUN_ID || "local"}-${process.env.GITHUB_RUN_ATTEMPT || "1"}-${randomUUID().slice(0, 8)}` } = {}) {
  if (!/^TrainMath-CI-[a-zA-Z0-9-]+$/.test(tag)) throw new Error("Invalid CI Simulator ownership tag");
  const inventory = await inventoryFrom(run), plan = selectSimulatorPlan(inventory);
  const existing = new Set(Object.values(inventory.devices || {}).flat().map(device => String(device.udid).toLowerCase()));
  const prepared = { format: "taiwan-train-math.ios-simulators", version: 1, owner: tag, runtime: plan.runtime, devices: [] };
  await ensureDirectory(output, { recursive: true });
  for (const model of plan.models) {
    const name = `${tag}-${model.kind}`;
    const udid = String(await run(["create", name, model.identifier, plan.runtime.identifier])).trim();
    if (!uuid(udid) || existing.has(udid.toLowerCase()) || prepared.devices.some(device => device.udid.toLowerCase() === udid.toLowerCase()))
      throw new Error("simctl create did not return a distinct new Simulator UUID");
    prepared.devices.push({ kind: model.kind, name, model: model.name, deviceTypeIdentifier: model.identifier, udid });
    // Retain ownership evidence even if a later create/boot command fails.
    await write(join(output, preparationName), JSON.stringify(prepared, null, 2));
  }
  await boot(run, prepared.devices.find(device => device.kind === "iphone").udid);
  return prepared;
}

function ownedDevices(prepared, inventory) {
  if (prepared?.format !== "taiwan-train-math.ios-simulators" || prepared.version !== 1
    || !/^TrainMath-CI-[a-zA-Z0-9-]+$/.test(prepared.owner) || !Array.isArray(prepared.devices) || prepared.devices.length !== 2)
    throw new Error("Invalid prepared Simulator ownership record");
  const runtime = (inventory.runtimes || []).find(runtime => runtime.identifier === prepared.runtime?.identifier
    && runtime.isAvailable === true && !runtime.availabilityError);
  if (!runtime) throw new Error("The prepared iOS runtime is no longer available");
  const actual = inventory.devices?.[runtime.identifier] || [], seen = new Set();
  return ["iphone", "ipad"].map(kind => {
    const device = prepared.devices.find(device => device.kind === kind);
    if (!device || !uuid(device.udid) || seen.has(device.udid.toLowerCase()) || device.name !== `${prepared.owner}-${kind}` || !typeId(device.deviceTypeIdentifier))
      throw new Error("Prepared Simulator IDs are not the expected CI-owned pair");
    const found = actual.find(item => String(item.udid).toLowerCase() === device.udid.toLowerCase() && item.isAvailable === true);
    if (!found || found.name !== device.name || found.deviceTypeIdentifier !== device.deviceTypeIdentifier)
      throw new Error("Prepared Simulator ownership does not match the current inventory");
    seen.add(device.udid.toLowerCase());
    return device;
  });
}

export async function smokeSimulators({ run = runSimctl, output = target, read = readFile, write = writeFile, ensureDirectory = mkdir,
  metadata = path => sharp(path).metadata(), stats = path => sharp(path).stats(),
  pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds)) } = {}) {
  let prepared;
  try { prepared = JSON.parse(await read(join(output, preparationName), "utf8")); }
  catch (error) {
    if (error.code !== "ENOENT") throw error;
    prepared = await prepareSimulators({ run, output, write, ensureDirectory });
  }
  const devices = ownedDevices(prepared, await inventoryFrom(run)), results = [], cleanupWarnings = [];
  let failure = null;
  try {
    for (const device of devices) {
      let stage = "boot";
      let coldFrameObservations = [];
      try {
        await boot(run, device.udid);
        stage = "bootstatus";
        await run(["bootstatus", device.udid, "-b"], { timeout: 600000 });
        await run(["ui", device.udid, "appearance", "light"]);
        await run(["status_bar", device.udid, "override", "--time", "9:41", "--batteryState", "charged", "--batteryLevel", "100"]);
        stage = "install";
        await run(["install", device.udid, appPath], { timeout: 360000 });
        stage = "launch";
        const launch = await run(["launch", device.udid, appId]);
        stage = "cold launch visual readiness";
        const firstPath = join(output, `${device.kind}-simulator-home.png`);
        const firstFrame = await waitForVisibleNativeFrame({
          capture: async index => {
            const path = join(output, `${device.kind}-simulator-cold-${index}.png`);
            await run(["io", device.udid, "screenshot", path]);
            return path;
          },
          inspect: async path => ({ ...(await metadata(path)), stats: await stats(path) }),
          pause,
          onObservation: observation => console.log(`${device.kind} cold frame ${observation.index}: entropy ${observation.entropy}, RGB deviation ${observation.meanRgbStdev}, visible ${observation.visible}`),
        });
        coldFrameObservations = firstFrame.observations;
        await copyFile(firstFrame.path, firstPath);
        stage = "relaunch";
        await run(["terminate", device.udid, appId]);
        await run(["launch", device.udid, appId]);
        await pause(12000);
        const relaunchPath = join(output, `${device.kind}-simulator-relaunch.png`);
        await run(["io", device.udid, "screenshot", relaunchPath]);
        const relaunchSize = await metadata(relaunchPath);
        if (relaunchSize.width !== firstFrame.width || relaunchSize.height !== firstFrame.height
          || !visibleNativeFrame(await stats(relaunchPath)))
          throw new Error("Native relaunch screenshot is still blank/splash");
        results.push({ kind: device.kind, device: device.model, simulatorName: device.name, udid: device.udid,
          runtime: prepared.runtime.identifier, width: firstFrame.width, height: firstFrame.height,
          launch: String(launch).trim(), status: "completed", coldFrameObservations,
          coldLaunchNonSplash: true, relaunchNonSplash: true });
        // Release the first device's processes before booting the tablet.
        await run(["shutdown", device.udid]);
      } catch (error) {
        coldFrameObservations = error.observations || coldFrameObservations;
        results.push({ kind: device.kind, device: device.model, udid: device.udid, status: "failed", stage,
          coldFrameObservations, error: summary(error) });
        throw error;
      }
    }
  } catch (error) { failure = error; }
  finally {
    // No "booted"/"all", erase, delete, or ID outside the verified fresh pair.
    for (const device of devices) {
      try { await run(["shutdown", device.udid]); }
      catch (error) {
        if (!String(error.stderr).includes("current state: Shutdown")) cleanupWarnings.push({ udid: device.udid, error: summary(error) });
      }
    }
  }
  const report = { appId, actualSimulator: true, preparationFile: preparationName, runtime: prepared.runtime, devices: results,
    tested: results.some(result => result.status === "completed") ? ["install", "cold launch", "process terminate and relaunch", "screenshots"] : [],
    notTested: ["physical device", "speaker output", "interactive gameplay"], cleanupWarnings };
  await write(join(output, "simulator-launch.json"), JSON.stringify(report, null, 2));
  if (failure) throw failure;
  if (cleanupWarnings.length) throw new Error("CI-owned Simulator cleanup failed; see simulator-launch.json");
  return report;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (args.length > 1 || (args.length === 1 && args[0] !== "--prepare")) throw new Error("Usage: node scripts/ios-simulator-smoke.mjs [--prepare]");
  if (args[0] === "--prepare") {
    const prepared = await prepareSimulators();
    console.log(`Created fresh CI-owned ${prepared.devices.map(device => device.model).join(" and ")} on ${prepared.runtime.name}; iPhone boot started.`);
  } else await smokeSimulators();
}
