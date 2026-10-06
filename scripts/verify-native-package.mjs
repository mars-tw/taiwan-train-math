import { readFile, stat } from "node:fs/promises";
import { createHash } from "node:crypto";
import { join } from "node:path";
const report = JSON.parse(await readFile("output/native/bundle-manifest.json", "utf8"));
const config = JSON.parse(await readFile("capacitor.config.json", "utf8"));
if (report.appId !== "tw.mars.trainmath" || config.webDir !== "dist-native" || config.server?.url || config.server?.cleartext) throw new Error("Invalid native package identity/server");
for (const file of report.files) {
  if (file.path.includes("..") || /(?:^|\/)(?:\.secrets|node_modules|\.audit-tmp|\.git)(?:\/|$)|\.(?:jks|keystore|p12|p8|mobileprovision)$/.test(file.path)) throw new Error("Private content in native package");
  const bytes = await readFile(join("dist-native", file.path));
  if (bytes.length !== file.bytes || createHash("sha256").update(bytes).digest("hex") !== file.sha256) throw new Error(`Native asset mismatch: ${file.path}`);
}
const paths = new Set(report.files.map(file => file.path));
for (const path of ["index.html", "native-host.js", "native-documents.js", "native-ui.css", "src/app.js", "src/native-runtime.js", "src/learning-guide.js", "data/trains.json", "privacy.html", "support.html"]) if (!paths.has(path)) throw new Error(`Missing native file: ${path}`);
const { trains } = JSON.parse(await readFile("dist-native/data/trains.json", "utf8"));
const photos = trains.flatMap(train => train.referencePhoto?.status === "verified" ? [train.referencePhoto.path] : []);
if (photos.length !== 58 || !photos.every(path => paths.has(path))) throw new Error("Missing verified train photographs");
const android = await readFile("android/app/src/main/AndroidManifest.xml", "utf8");
if (android.includes('android.permission.INTERNET') || !android.includes('android:allowBackup="false"')) throw new Error("Unexpected native data/network configuration");
const iosProject = await readFile("ios/App/App.xcodeproj/project.pbxproj", "utf8");
if (!iosProject.includes("PrivacyInfo.xcprivacy in Resources") || !iosProject.includes("OfflineSpeechPlugin.swift in Sources")) throw new Error("Native Apple features are not in the app target");
const privacy = await readFile("ios/App/App/PrivacyInfo.xcprivacy", "utf8");
if (!privacy.includes("CA92.1") || !privacy.includes("NSPrivacyTracking")) throw new Error("Missing Apple privacy declarations");
await stat("ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png");
console.log(JSON.stringify({ status: "VERIFIED", appId: report.appId, localFiles: paths.size, verifiedPhotos: photos.length, bytes: report.bytes, remoteServer: false }));
