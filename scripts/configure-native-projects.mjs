import { createRequire } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const xcode = require("xcode");
const file = "ios/App/App.xcodeproj/project.pbxproj";
const project = xcode.project(file); project.parseSync();
const target = project.getFirstTarget().uuid;
const appGroup = project.findPBXGroupKey({ path: "App" });
if (!target || !appGroup) throw new Error("Missing native iOS app target");
for (const name of ["OfflineSpeechPlugin.swift", "TrainMathViewController.swift"]) {
  if (!project.hasFile(name)) project.addSourceFile(name, { target }, appGroup);
}
let resourcesGroup = project.findPBXGroupKey({ name: "Resources" });
if (!resourcesGroup) {
  resourcesGroup = project.addPbxGroup([], "Resources").uuid;
  project.addToPbxGroup(resourcesGroup, appGroup);
}
if (!project.hasFile("PrivacyInfo.xcprivacy")) project.addResourceFile("PrivacyInfo.xcprivacy", { target }, resourcesGroup);
for (const reference of Object.values(project.pbxFileReferenceSection())) {
  if (!reference || typeof reference !== "object") continue;
  for (const key of Object.keys(reference)) if (reference[key] === undefined || reference[key] === "undefined") delete reference[key];
  if (String(reference.path).includes("PrivacyInfo.xcprivacy")) reference.lastKnownFileType = "text.xml";
}
for (const group of Object.values(project.hash.project.objects.PBXGroup)) {
  if (group && typeof group === "object" && group.path === "undefined") delete group.path;
}
writeFileSync(file, project.writeSync().replaceAll("IPHONEOS_DEPLOYMENT_TARGET = 15.0;", "IPHONEOS_DEPLOYMENT_TARGET = 15.4;").replaceAll("MARKETING_VERSION = 1.0;", "MARKETING_VERSION = 1.0.0;"));
const storyboardPath = "ios/App/App/Base.lproj/Main.storyboard";
writeFileSync(storyboardPath, readFileSync(storyboardPath, "utf8").replace('customClass="CAPBridgeViewController" customModule="Capacitor"', 'customClass="TrainMathViewController" customModule="App"'));
console.log("iOS 原生語音與隱私資訊已加入 App target。");
