import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import sharp from "sharp";
const target = "output/native-artifacts/ios";
await mkdir(target, { recursive: true });
const run = args => execFileSync("xcrun", ["simctl", ...args], { encoding: "utf8", timeout: 180000 });
const inventory = JSON.parse(run(["list", "devices", "available", "--json"]));
const devices = Object.values(inventory.devices).flat().filter(item => item.isAvailable);
const iphone = devices.find(item => /^iPhone/.test(item.name) && /Pro Max/.test(item.name)) || devices.find(item => /^iPhone/.test(item.name));
const ipad = devices.find(item => /^iPad Pro/.test(item.name) && /13-inch|12.9-inch/.test(item.name)) || devices.find(item => /^iPad/.test(item.name));
if (!iphone || !ipad) throw new Error("Both iPhone and iPad Simulator runtimes are required");
const results = [];
for (const [kind, device] of [["iphone", iphone], ["ipad", ipad]]) {
  try {
    try { run(["boot", device.udid]); } catch (error) { if (!String(error.stderr).includes("current state: Booted")) throw error; }
    run(["bootstatus", device.udid, "-b"]);
    run(["ui", device.udid, "appearance", "light"]);
    run(["status_bar", device.udid, "override", "--time", "9:41", "--batteryState", "charged", "--batteryLevel", "100"]);
    run(["install", device.udid, "output/ios-derived/Build/Products/Debug-iphonesimulator/App.app"]);
    const launch = run(["launch", device.udid, "tw.mars.trainmath"]);
    await new Promise(resolve => setTimeout(resolve, 7000));
    const firstPath = `${target}/${kind}-simulator-home.png`;
    run(["io", device.udid, "screenshot", firstPath]);
    const dimensions = await sharp(firstPath).metadata();
    run(["terminate", device.udid, "tw.mars.trainmath"]);
    run(["launch", device.udid, "tw.mars.trainmath"]);
    await new Promise(resolve => setTimeout(resolve, 4000));
    run(["io", device.udid, "screenshot", `${target}/${kind}-simulator-relaunch.png`]);
    results.push({ kind, device: device.name, width: dimensions.width, height: dimensions.height, launch: launch.trim() });
  } finally { run(["shutdown", device.udid]); }
}
await writeFile(`${target}/simulator-launch.json`, JSON.stringify({ appId: "tw.mars.trainmath", actualSimulator: true, devices: results, tested: ["install", "cold launch", "process terminate and relaunch", "screenshots"], notTested: ["physical device", "speaker output", "interactive gameplay"] }, null, 2));
