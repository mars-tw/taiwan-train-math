// Bounded, unsigned Simulator capture of the unchanged, verifier-bound 47 files.
import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { createWriteStream } from 'node:fs';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { runAppiumSession } from './godot-appium-session.mjs';

const scripts = path.dirname(fileURLToPath(import.meta.url));
const MODES = Object.freeze({
  'seven-appium': { project: 'seven-district-reckoning', name: 'SevenDistrict', appId: 'tw.mars.sevendistrictreckoning', kinds: ['iphone', 'ipad'] },
  'crack-phone': { project: 'crackveil-vanguard', name: 'CrackveilVanguard', appId: 'tw.mars.crackveilvanguard', kinds: ['iphone'] },
  'crack-store-phone': { project: 'crackveil-vanguard', name: 'CrackveilVanguard', appId: 'tw.mars.crackveilvanguard', kinds: ['iphone'] },
});
const PIXELS = { iphone: [1320, 2868], ipad: [2064, 2752] };
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const TYPE = /^com\.apple\.CoreSimulator\.SimDeviceType\.[A-Za-z0-9.-]+$/;
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const inside = (parent, target) => {
  const relative = path.relative(parent, target);
  return relative === '' || (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative));
};
class CaptureError extends Error {
  constructor(code) { super(code); this.name = 'BoundedCaptureError'; this.code = code; }
}
const fail = code => { throw new CaptureError(code); };
const errorCode = error => error instanceof CaptureError ? error.code : 'LOCAL_CAPTURE_FAILED';

export function selectCapturePlan(inventory, mode) {
  if (!Object.hasOwn(MODES, mode)) fail('INVALID_MODE');
  const runtimes = (inventory?.runtimes || []).filter(runtime => runtime.isAvailable === true && !runtime.availabilityError
    && /^26\.2(?:\.0)?$/.test(runtime.version || '') && /^com\.apple\.CoreSimulator\.SimRuntime\.iOS-26-2(?:-0)?$/.test(runtime.identifier || ''));
  if (runtimes.length !== 1) fail('EXACT_IOS_26_2_RUNTIME_REQUIRED');
  const runtime = runtimes[0], encoded = 26 * 65536 + 2 * 256;
  const compatible = (inventory.devicetypes || []).filter(model => TYPE.test(model.identifier || '')
    && Number.isFinite(model.minRuntimeVersion) && Number.isFinite(model.maxRuntimeVersion)
    && model.minRuntimeVersion <= encoded && encoded <= model.maxRuntimeVersion);
  const phones = compatible.filter(model => model.name === 'iPhone 17 Pro Max');
  const tablets = compatible.filter(model => /^iPad Pro 13-inch \(M4\)(?: \([^)]*\))?$/.test(model.name || ''))
    .sort((a, b) => Number(!a.name.includes('16GB')) - Number(!b.name.includes('16GB')) || a.identifier.localeCompare(b.identifier));
  if (phones.length !== 1 || (mode === 'seven-appium' && !tablets.length)) fail('EXACT_NATIVE_MODELS_REQUIRED');
  return { runtime: { identifier: runtime.identifier, version: runtime.version, name: runtime.name },
    models: MODES[mode].kinds.map(kind => ({ kind, ...(kind === 'iphone' ? phones[0] : tablets[0]) })) };
}

// Vision boxes refer to the orientation-corrected image. Keep the inverse EXIF
// point as evidence, then use actual WDA window dimensions and scale for tap units.
// WDA v11.4.0 FBElementCommands.m: gestureCoordinateWithOffset uses the active
// application's (0,0) coordinate plus the supplied point, with no extra rotation.
// https://raw.githubusercontent.com/appium/WebDriverAgent/v11.4.0/WebDriverAgentLib/Commands/FBElementCommands.m
// https://raw.githubusercontent.com/appium/appium-xcuitest-driver/v10.43.0/lib/commands/general.ts
export function deriveTapPoint(vision, screen, windowRect) {
  const geometry = vision?.geometry, button = vision?.startButton;
  if (!geometry || button?.label !== '開始新遊戲' || !Number.isFinite(button.confidence) || button.confidence <= 0.3)
    fail('VISIBLE_START_LABEL_UNCONFIRMED');
  const b = button.bbox;
  if (!b || !['x', 'y', 'width', 'height'].every(key => Number.isFinite(b[key])) || b.x < 0 || b.y < 0
    || b.width <= 0 || b.height <= 0 || b.x + b.width > 1.000001 || b.y + b.height > 1.000001)
    fail('VISIBLE_START_GEOMETRY_INVALID');
  const { width, height, exifOrientation, semanticWidth, semanticHeight } = geometry;
  if (![width, height, semanticWidth, semanticHeight].every(value => Number.isInteger(value) && value > 0)
    || ![1, 3, 6, 8].includes(exifOrientation) || semanticWidth <= semanticHeight) fail('NATIVE_ORIENTATION_UNCONFIRMED');
  const quarterTurn = [6, 8].includes(exifOrientation);
  if (semanticWidth !== (quarterTurn ? height : width) || semanticHeight !== (quarterTurn ? width : height))
    fail('NATIVE_ORIENTATION_UNCONFIRMED');
  const scale = screen?.scale;
  const values = [scale, screen?.screenSize?.width, screen?.screenSize?.height,
    windowRect?.x, windowRect?.y, windowRect?.width, windowRect?.height];
  if (!values.every(Number.isFinite) || scale <= 0 || scale > 4 || windowRect.x !== 0 || windowRect.y !== 0
    || Math.abs(windowRect.width * scale - semanticWidth) > 1 || Math.abs(windowRect.height * scale - semanticHeight) > 1)
    fail('ACTUAL_WDA_POINT_SPACE_UNCONFIRMED');
  const screenPixels = [screen.screenSize.width * scale, screen.screenSize.height * scale].sort((a, b) => a - b);
  const nativePixels = [width, height].sort((a, b) => a - b);
  if (screenPixels.some((value, index) => Math.abs(value - nativePixels[index]) > 1)) fail('ACTUAL_WDA_POINT_SPACE_UNCONFIRMED');
  const normalized = { x: b.x + b.width / 2, y: 1 - (b.y + b.height / 2) };
  let encoded;
  if (exifOrientation === 6) encoded = { x: normalized.y * width, y: (1 - normalized.x) * height };
  else if (exifOrientation === 8) encoded = { x: (1 - normalized.y) * width, y: normalized.x * height };
  else if (exifOrientation === 3) encoded = { x: (1 - normalized.x) * width, y: (1 - normalized.y) * height };
  else encoded = { x: normalized.x * width, y: normalized.y * height };
  const semanticPixel = { x: normalized.x * semanticWidth, y: normalized.y * semanticHeight };
  const point = { x: semanticPixel.x / scale, y: semanticPixel.y / scale };
  if (point.x <= 0 || point.y <= 0 || point.x >= windowRect.width || point.y >= windowRect.height)
    fail('VISIBLE_START_POINT_OUTSIDE_APP');
  return { label: button.label, confidence: button.confidence, bbox: { ...b }, exifOrientation,
    encodedPixelFromExifInverse: encoded, semanticPixel, screenPoint: point,
    pointSpace: 'active-XCTest-application-origin', actualScale: scale,
    actualWindowRect: { x: windowRect.x, y: windowRect.y, width: windowRect.width, height: windowRect.height },
    pixelAndPointDimensionsVerified: true };
}

const imageHelper = `import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import Vision
func stop() -> Never { exit(2) }
guard CommandLine.arguments.count == 4 else { stop() }
let input = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
let recognize = CommandLine.arguments[3] == "start"
guard let source = CGImageSourceCreateWithURL(input as CFURL, nil),
let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { stop() }
let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [String:Any] ?? [:]
let exif = (properties[kCGImagePropertyOrientation as String] as? NSNumber)?.intValue ?? 1
guard [1,3,6,8].contains(exif), let orientation = CGImagePropertyOrientation(rawValue: UInt32(exif)),
let context = CGContext(data: nil, width: image.width, height: image.height,
bitsPerComponent: 8, bytesPerRow: image.width * 4, space: CGColorSpaceCreateDeviceRGB(),
bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { stop() }
context.draw(image, in: CGRect(x: 0, y: 0, width: CGFloat(image.width), height: CGFloat(image.height)))
guard let rgb = context.makeImage(),
let destination = CGImageDestinationCreateWithURL(output as CFURL, UTType.png.identifier as CFString, 1, nil) else { stop() }
CGImageDestinationAddImage(destination, rgb, [kCGImagePropertyOrientation as String: exif] as CFDictionary)
guard CGImageDestinationFinalize(destination) else { stop() }
let quarterTurn = [6,8].contains(exif)
let geometry: [String:Any] = ["width":image.width,"height":image.height,"exifOrientation":exif,
"semanticWidth":quarterTurn ? image.height : image.width,"semanticHeight":quarterTurn ? image.width : image.height]
var button: Any = NSNull()
if recognize {
 let request = VNRecognizeTextRequest()
 request.recognitionLevel = .accurate
 request.recognitionLanguages = ["zh-Hant", "en-US"]
 request.usesLanguageCorrection = false
 request.customWords = ["開始新遊戲"]
 let handler = VNImageRequestHandler(cgImage: image, orientation: orientation, options: [:])
 do { try handler.perform([request]) } catch { stop() }
 let matches = (request.results ?? []).compactMap { observation -> [String:Any]? in
  guard let text = observation.topCandidates(1).first, text.string == "開始新遊戲", text.confidence > 0.3 else { return nil }
  let b = observation.boundingBox
  return ["label":text.string,"confidence":Double(text.confidence),
  "bbox":["x":Double(b.origin.x),"y":Double(b.origin.y),"width":Double(b.width),"height":Double(b.height)]]
 }
 if matches.count == 1 { button = matches[0] }
}
guard let json = try? JSONSerialization.data(withJSONObject: ["geometry":geometry,"startButton":button], options: [.sortedKeys]),
let text = String(data: json, encoding: .utf8) else { stop() }
print(text)
`;

const consoleDiagnostics = raw => raw.split(/\r?\n/).filter(line => /^(?:SCRIPT ERROR:|ERROR:)/.test(line)).slice(-20).map(line => ({
  kind: line.startsWith('SCRIPT ERROR:') ? 'SCRIPT ERROR' : 'ERROR',
  summary: line.replace(/https?:\/\/[^\s"'<>]+/g, '<url>')
    .replace(/\/(?:Users|private|var|Volumes|tmp)\/[^\s"'<>]+/g, '<path>')
    .replace(/\b(?:password|secret|token|api[_-]?key)\s*[:=]\s*[^\s,;]+/gi, '<redacted>')
    .replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, 400),
}));

export async function captureNative({ mode, source, metadata, verifier, output } = {}) {
  if (!Object.hasOwn(MODES, mode) || process.platform !== 'darwin' || process.arch !== 'x64' || !process.env.RUNNER_TEMP)
    fail('APPROVED_MODE_AND_INTEL_MAC_REQUIRED');
  if (![source, metadata, verifier, output].every(value => typeof value === 'string' && path.isAbsolute(value))) fail('ABSOLUTE_CAPTURE_PATHS_REQUIRED');
  const recipe = MODES[mode], runnerTemp = await fs.realpath(process.env.RUNNER_TEMP);
  source = await fs.realpath(source); metadata = await fs.realpath(metadata); verifier = await fs.realpath(verifier);
  await fs.mkdir(output, { recursive: true }); output = await fs.realpath(output);
  if ((await fs.readdir(output)).length !== 0 || inside(source, output) || inside(output, source)) fail('FRESH_SEPARATE_OUTPUT_REQUIRED');
  const scratch = await fs.mkdtemp(path.join(runnerTemp, 'godot-bounded-capture-'));
  await fs.chmod(scratch, 0o700);
  if (inside(output, scratch) || inside(scratch, output) || inside(source, scratch)) fail('PRIVATE_SCRATCH_REQUIRED');
  const report = { format: 'godot.bounded-native-capture', version: 1, mode, projectId: recipe.project, appId: recipe.appId,
    status: 'failed', stage: 'prepare', actualSimulator: false, actualAppium: false, runtime: null,
    sameOriginal47Files: false, unsignedSimulatorLinkOnly: false, signedIpaRebuilt: false, signerSecretsUsed: false,
    sourceOrPckModified: null, sourceStill47VerifiedAfterLink: false,
    screenshotResized: false, rawLogsUploaded: false, accessibilityInteraction: false,
    gameplayPassed: null, manualVisualReviewRequired: true, physicalDeviceTested: false, speakerOutputTested: false,
    storeUploadPerformed: false, results: [], cleanup: [], commandFailures: [] };
  const owned = [], processes = new Set(); let sequence = 0;
  const publish = () => fs.writeFile(path.join(output, 'bounded-native-capture.json'), JSON.stringify(report, null, 2));

  async function startProcess(label, args, timeout) {
    if (!/^[a-z0-9-]+$/.test(label) || !Array.isArray(args) || !Number.isInteger(timeout) || timeout < 1) fail('COMMAND_CONTRACT_INVALID');
    const logPath = path.join(scratch, `${String(++sequence).padStart(3, '0')}-${label}.log`);
    const log = createWriteStream(logPath, { flags: 'wx', mode: 0o600 });
    let logFailed = false, bytes = 0, stdoutBytes = 0, closed = false, timedOut = false, spawnFailed = false, exitCode = null;
    const stdout = [];
    log.on('error', () => { logFailed = true; });
    try { await new Promise((resolve, reject) => { log.once('open', resolve); log.once('error', reject); }); }
    catch { fail('PRIVATE_COMMAND_LOG_FAILED'); }
    const child = spawn(args[0], args.slice(1), { stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, TMPDIR: scratch }, windowsHide: true });
    const append = chunk => { if (!logFailed && bytes < 20 * 1024 * 1024) {
      const retained = chunk.subarray(0, 20 * 1024 * 1024 - bytes); bytes += retained.length; log.write(retained);
    } };
    const appendStdout = chunk => {
      append(chunk);
      if (stdoutBytes < 8 * 1024 * 1024) {
        const retained = chunk.subarray(0, 8 * 1024 * 1024 - stdoutBytes); stdoutBytes += retained.length; stdout.push(retained);
      }
    };
    child.stdout.on('data', appendStdout); child.stderr.on('data', append);
    child.once('error', () => { spawnFailed = true; });
    const finished = new Promise(resolve => child.once('close', code => { closed = true; exitCode = code; resolve(); }));
    let forceTimer;
    const timer = setTimeout(() => { timedOut = true; child.kill('SIGTERM'); forceTimer = setTimeout(() => { if (!closed) child.kill('SIGKILL'); }, 5000); }, timeout);
    const record = { child, finished, get closed() { return closed; }, get timedOut() { return timedOut; },
      async stop() {
        clearTimeout(timer); clearTimeout(forceTimer);
        if (!closed) child.kill('SIGTERM');
        let stopTimer;
        try { await Promise.race([finished, new Promise(resolve => { stopTimer = setTimeout(resolve, 5000); })]); }
        finally { clearTimeout(stopTimer); }
        if (!closed) {
          child.kill('SIGKILL');
          try { await Promise.race([finished, new Promise(resolve => { stopTimer = setTimeout(resolve, 5000); })]); }
          finally { clearTimeout(stopTimer); }
        }
        if (!closed) fail('OWNED_PROCESS_STOP_UNCONFIRMED');
      },
      async result() {
        let endTimer;
        try { await Promise.race([finished, new Promise(resolve => { endTimer = setTimeout(resolve, timeout + 10000); })]); }
        finally { clearTimeout(endTimer); }
        if (!closed) await record.stop();
        clearTimeout(timer); clearTimeout(forceTimer);
        child.stdout.removeListener('data', appendStdout); child.stderr.removeListener('data', append);
        if (!log.destroyed && !log.writableFinished) await new Promise(resolve => { log.once('finish', resolve); log.once('error', resolve); log.end(); });
        processes.delete(record);
        if (logFailed) fail('PRIVATE_COMMAND_LOG_FAILED');
        return { code: spawnFailed ? -1 : exitCode, timedOut, text: await fs.readFile(logPath, 'utf8'), stdout: Buffer.concat(stdout).toString('utf8') };
      },
    };
    processes.add(record); return record;
  }
  async function command(label, args, { timeout = 180000, allowFailure = false } = {}) {
    const result = await (await startProcess(label, args, timeout)).result();
    if (result.code !== 0 || result.timedOut) {
      report.commandFailures.push({ command: label, code: result.code, timedOut: result.timedOut });
      if (!allowFailure) fail(result.timedOut ? 'BOUNDED_COMMAND_TIMED_OUT' : 'BOUNDED_COMMAND_FAILED');
    }
    return result;
  }
  async function inventory() { return JSON.parse((await command('simulator-inventory', ['xcrun', 'simctl', 'list', '--json'])).stdout); }
  async function confirmOwned(device) {
    const current = await inventory();
    const matches = (current.devices?.[device.runtime] || []).filter(item => item.udid?.toLowerCase() === device.udid.toLowerCase()
      && item.name === device.name && item.deviceTypeIdentifier === device.deviceTypeIdentifier && item.isAvailable === true);
    if (matches.length !== 1) fail('OWNED_SIMULATOR_IDENTITY_UNCONFIRMED');
    return matches[0];
  }
  async function stopConsole(console, result, phase) {
    if (!console) return;
    await console.stop();
    const capture = await console.result();
    result.ownGameConsoleDiagnostics.push(...consoleDiagnostics(capture.text).map(item => ({ phase, ...item })));
    if (capture.timedOut) fail('OWN_GAME_CONSOLE_TIMED_OUT');
  }
  async function rawShot(device, stage, recognize = false) {
    const rawFile = `raw-screenshots/${device.kind}-${stage}-raw.png`, rgbFile = `screenshots/${device.kind}-${stage}.png`;
    const rawPath = path.join(output, rawFile), rgbPath = path.join(output, rgbFile);
    await command(device.kind + '-' + stage + '-raw', ['xcrun', 'simctl', 'io', device.udid, 'screenshot', '--type=png', rawPath]);
    const raw = await fs.readFile(rawPath);
    if (raw.length < 33 || raw.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') fail('ORIGINAL_SIMCTL_PNG_REQUIRED');
    const width = raw.readUInt32BE(16), height = raw.readUInt32BE(20), expected = PIXELS[device.kind];
    if (![width, height].sort((a, b) => a - b).every((value, index) => value === expected[index])) fail('ACTUAL_NATIVE_PIXEL_SIZE_MISMATCH');
    const shot = { stage, rawFile, rawSha256: sha(raw), rawBytes: raw.length, width, height,
      originalSimctlPng: true, screenshotResized: false, rgbFile: null };
    device.result.screenshots.push(shot);
    await publish(); // Preserve original pixels even if helper/OCR/point validation fails.
    const helper = await command(device.kind + '-' + stage + '-geometry', ['xcrun', 'swift', path.join(scratch, 'native-image.swift'), rawPath, rgbPath, recognize ? 'start' : 'metadata'], { timeout: 180000 });
    const vision = JSON.parse(helper.stdout.trim());
    if (vision.geometry?.width !== width || vision.geometry?.height !== height || ![1, 3, 6, 8].includes(vision.geometry?.exifOrientation)) fail('NATIVE_IMAGE_METADATA_UNCONFIRMED');
    const rgb = await fs.readFile(rgbPath);
    if (rgb.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a' || rgb[25] !== 2
      || rgb.readUInt32BE(16) !== width || rgb.readUInt32BE(20) !== height) fail('UNRESIZED_RGB_COPY_REQUIRED');
    Object.assign(shot, { rgbFile, rgbSha256: sha(rgb), rgbBytes: rgb.length, rgbNoAlpha: true,
      exifOrientation: vision.geometry.exifOrientation, semanticWidth: vision.geometry.semanticWidth,
      semanticHeight: vision.geometry.semanticHeight, rgbPreservesNativeOrientation: true });
    await publish(); return { shot, vision };
  }

  try {
    report.stage = 'xcode-guard';
    const xcode = await command('xcode-version', ['xcodebuild', '-version']);
    if (!/^Xcode 26\.3\s+Build version 17C529\s*$/.test(xcode.stdout.trim())) fail('EXACT_XCODE_26_3_REQUIRED');
    report.xcode = { version: '26.3', build: '17C529', runnerArchitecture: 'x86_64' };
    report.stage = 'source-verification';
    await command('source-verify', ['python3', verifier, 'source', '--root', source, '--metadata', metadata,
      '--project', recipe.project, '--output', path.join(output, 'source-verification.json')]);
    report.sameOriginal47Files = true;
    const lib = path.join(source, recipe.name + '.xcframework/ios-arm64_x86_64-simulator/libgodot.a');
    const architecture = await command('original-library-architecture', ['xcrun', 'lipo', '-archs', lib]);
    if (architecture.stdout.trim() !== 'x86_64') fail('ACTUAL_X86_64_LIBRARY_REQUIRED');
    report.stage = 'unsigned-simulator-link';
    await command('unsigned-sim-link', ['xcodebuild', '-project', path.join(source, recipe.name + '.xcodeproj'), '-scheme', recipe.name,
      '-configuration', 'Debug', '-sdk', 'iphonesimulator', '-destination', 'generic/platform=iOS Simulator',
      '-derivedDataPath', path.join(scratch, 'derived-game'), 'CODE_SIGNING_ALLOWED=NO', 'ARCHS=x86_64',
      'EXCLUDED_ARCHS=arm64', 'ONLY_ACTIVE_ARCH=NO', 'build'], { timeout: 2400000 });
    const app = path.join(scratch, 'derived-game/Build/Products/Debug-iphonesimulator', recipe.name + '.app');
    const checkedApp = await command('unsigned-app-verify', ['python3', verifier, 'app', '--root', source, '--project', recipe.project,
      '--app', app, '--output', path.join(output, 'simulator-verification.json')]);
    if (JSON.stringify(JSON.parse(checkedApp.stdout).architectures) !== '["x86_64"]') fail('ACTUAL_X86_64_APP_REQUIRED');
    await command('source-verify-after-link', ['python3', verifier, 'source', '--root', source, '--metadata', metadata,
      '--project', recipe.project, '--output', path.join(output, 'source-verification-after-link.json')]);
    report.sourceStill47VerifiedAfterLink = true; report.sourceOrPckModified = false;
    report.unsignedSimulatorLinkOnly = true;
    await fs.writeFile(path.join(scratch, 'native-image.swift'), imageHelper, { flag: 'wx', mode: 0o600 });
    await fs.mkdir(path.join(output, 'raw-screenshots')); await fs.mkdir(path.join(output, 'screenshots'));
    const initial = await inventory(), plan = selectCapturePlan(initial, mode);
    report.runtime = plan.runtime;
    const previous = new Set(Object.values(initial.devices || {}).flat().map(device => String(device.udid).toLowerCase()));
    for (const model of plan.models) {
      report.stage = model.kind + '-capture';
      const name = `Mars-Bounded-${mode}-${model.kind}-${randomUUID().slice(0, 12)}`;
      const udid = (await command(model.kind + '-create', ['xcrun', 'simctl', 'create', name, model.identifier, plan.runtime.identifier])).stdout.trim();
      if (!UUID.test(udid) || previous.has(udid.toLowerCase()) || owned.some(item => item.udid.toLowerCase() === udid.toLowerCase())) fail('FRESH_OWNED_SIMULATOR_REQUIRED');
      const result = { device: model.kind, model: model.name, udid, simulatorName: name, status: 'failed', screenshots: [],
        ownGameConsoleDiagnostics: [], actualAppium: false, coldForegroundConfirmed: null, warmForegroundConfirmed: null,
        visibleStartLabelTapped: false, gameplayPassed: null, manualVisualReviewRequired: true };
      const device = { kind: model.kind, model: model.name, udid, name, deviceTypeIdentifier: model.identifier, runtime: plan.runtime.identifier, result };
      owned.push(device); report.results.push(result); await publish();
      await confirmOwned(device);
      await command(model.kind + '-boot', ['xcrun', 'simctl', 'boot', udid]);
      await command(model.kind + '-bootstatus', ['xcrun', 'simctl', 'bootstatus', udid, '-b'], { timeout: 600000 });
      report.actualSimulator = true;
      await command(model.kind + '-install', ['xcrun', 'simctl', 'install', udid, app], { timeout: 360000 });
      let coldConsole, warmConsole;
      try {
        coldConsole = await startProcess(model.kind + '-cold-own-game-console', ['xcrun', 'simctl', 'launch', '--console-pty', udid, recipe.appId], 900000);
        if (mode === 'crack-store-phone') {
          const runner = path.join(scratch, 'store-phone-runner'), derived = path.join(scratch, 'derived-store-tests');
          await command('generate-screen-only-runner', ['python3', path.join(scripts, 'create-godot-store-screen-project.py'), runner]);
          await command('build-screen-only-runner', ['xcodebuild', '-project', path.join(runner, 'Capture.xcodeproj'), '-scheme', 'Capture',
            '-sdk', 'iphonesimulator', '-destination', 'generic/platform=iOS Simulator', '-derivedDataPath', derived,
            'CODE_SIGNING_ALLOWED=NO', 'ARCHS=x86_64', 'EXCLUDED_ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES', 'build-for-testing'], { timeout: 600000 });
          const resultPath = path.join(scratch, 'screen-only.xcresult');
          const test = await command('screen-only-xctest', ['xcodebuild', '-project', path.join(runner, 'Capture.xcodeproj'), '-scheme', 'Capture',
            '-destination', 'platform=iOS Simulator,id=' + udid, '-derivedDataPath', derived, '-resultBundlePath', resultPath,
            '-parallel-testing-enabled', 'NO', 'CODE_SIGNING_ALLOWED=NO', 'ARCHS=x86_64', 'EXCLUDED_ARCHS=arm64',
            'ONLY_ACTIVE_ARCH=YES', 'test-without-building'], { timeout: 900000, allowFailure: true });
          result.actualXCTestExit = test.code; result.actualXCTest = true; result.frameAccessibilityQueryUsed = false;
          const phases = test.text.split(/\r?\n/).filter(line => /^STORE_SCREEN_(?:PRE_CAPTURE|PHASE|RAW_SHA256)=/.test(line));
          result.screenOnlyPhases = phases.slice(-15);
          const geometry = test.text.split(/\r?\n/).filter(line => line.startsWith('STORE_SCREEN_GEOMETRY=')).map(line => {
            const data = JSON.parse(line.slice('STORE_SCREEN_GEOMETRY='.length));
            if (!['cold90', 'warm90'].includes(data.stage) || !['deviceOrientation', 'imageOrientation', 'imageWidth', 'imageHeight',
              'imageScale', 'cgWidth', 'cgHeight', 'pngOrientation'].every(key => Number.isFinite(data[key]))) fail('SCREEN_ONLY_GEOMETRY_INVALID');
            return data;
          });
          result.screenOnlyGeometry = geometry;
          const exported = path.join(scratch, 'screen-only-attachments'); await fs.mkdir(exported);
          const exportedResult = await command('export-screen-only-attachments', ['xcrun', 'xcresulttool', 'export', 'attachments',
            '--path', resultPath, '--output-path', exported], { allowFailure: true });
          if (exportedResult.code === 0) {
            const manifest = JSON.parse(await fs.readFile(path.join(exported, 'manifest.json'), 'utf8'));
            const walk = node => Array.isArray(node) ? node.flatMap(walk) : !node || typeof node !== 'object' ? []
              : (typeof node.exportedFileName === 'string' ? [node] : []).concat(Object.values(node).flatMap(walk));
            const selected = walk(manifest).filter(item => /^iphone-(cold90|warm90)-raw(?:[^A-Za-z0-9]|$)/.test(String(item.suggestedHumanReadableName || '')));
            for (const item of selected) {
              const stage = String(item.suggestedHumanReadableName).match(/^iphone-(cold90|warm90)-raw/)[1];
              if (!/^[A-Za-z0-9_.-]+\.png$/i.test(item.exportedFileName) || result.screenshots.some(shot => shot.stage === stage)) fail('ORIGINAL_SCREEN_ATTACHMENT_REQUIRED');
              const rawFile = `raw-screenshots/iphone-${stage}-raw.png`, rgbFile = `screenshots/iphone-${stage}.png`;
              const raw = await fs.readFile(path.join(exported, item.exportedFileName));
              await fs.writeFile(path.join(output, rawFile), raw, { flag: 'wx' });
              if (raw.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') fail('ORIGINAL_SCREEN_ATTACHMENT_REQUIRED');
              const shot = { stage, rawFile, rawSha256: sha(raw), rawBytes: raw.length, originalXCUIScreenPng: true, screenshotResized: false };
              result.screenshots.push(shot); await publish();
              const image = await command('screen-only-' + stage + '-image-info', ['xcrun', 'swift', path.join(scratch, 'native-image.swift'),
                path.join(output, rawFile), path.join(output, rgbFile), 'metadata']);
              const metadata = JSON.parse(image.stdout), g = geometry.find(item => item.stage === stage), exifs = [1, 3, 8, 6, 2, 4, 5, 7];
              const rgb = await fs.readFile(path.join(output, rgbFile));
              if (!g || g.deviceOrientation !== 4 || g.imageWidth <= g.imageHeight || g.imageWidth * g.imageScale !== 2868
                || g.imageHeight * g.imageScale !== 1320 || exifs[g.imageOrientation] !== metadata.geometry.exifOrientation
                || metadata.geometry.semanticWidth !== 2868 || metadata.geometry.semanticHeight !== 1320
                || raw.readUInt32BE(16) !== g.cgWidth || raw.readUInt32BE(20) !== g.cgHeight || rgb[25] !== 2
                || rgb.readUInt32BE(16) !== g.cgWidth || rgb.readUInt32BE(20) !== g.cgHeight) fail('NATIVE_LANDSCAPE_SCREEN_CONTRACT_FAILED');
              Object.assign(shot, { width:g.cgWidth, height:g.cgHeight, rgbFile, rgbSha256:sha(rgb), rgbBytes:rgb.length, rgbNoAlpha:true,
                exifOrientation:metadata.geometry.exifOrientation, semanticWidth:2868, semanticHeight:1320,
                nativeDeviceLandscapeOrientationVerified:true, storePixelsRequireVisualReview:true });
              await publish();
            }
          }
          if (test.code !== 0 || test.timedOut || result.screenshots.length !== 2) fail('SCREEN_ONLY_XCTEST_FAILED');
          result.status = 'completed';
        } else if (mode === 'crack-phone') {
          await pause(90000);
          result.consoleSurvivedColdWait = !coldConsole.closed;
          await rawShot(device, 'cold90');
          if (!result.consoleSurvivedColdWait) fail('OWN_GAME_EXITED_BEFORE_COLD_CAPTURE');
          await command(model.kind + '-terminate', ['xcrun', 'simctl', 'terminate', udid, recipe.appId]);
          await stopConsole(coldConsole, result, 'cold'); coldConsole = null;
          warmConsole = await startProcess(model.kind + '-warm-own-game-console', ['xcrun', 'simctl', 'launch', '--console-pty', udid, recipe.appId], 900000);
          await pause(90000);
          result.consoleSurvivedWarmWait = !warmConsole.closed;
          await rawShot(device, 'warm90');
          if (!result.consoleSurvivedWarmWait) fail('OWN_GAME_EXITED_BEFORE_WARM_CAPTURE');
          result.status = 'completed';
        } else {
          const appium = await runAppiumSession({ appiumBin: path.join(scripts, 'godot-appium-runtime/node_modules/appium/index.js'),
            udid, bundleId: recipe.appId, model: model.name, platformVersion: plan.runtime.version, output, scratch,
            observeStart: async ({ execute, getWindowRect }) => {
              const observation = { coldCaptured: false, startTapped: false, afterStartCaptured: false, warmCaptured: false };
              try {
                const foreground = async () => {
                  const active = await execute('mobile: activeAppInfo', {});
                  const state = await execute('mobile: queryAppState', { bundleId: recipe.appId });
                  if (active?.bundleId !== recipe.appId || state !== 4) fail('OWN_GAME_FOREGROUND_UNCONFIRMED');
                };
                // WDA startup may foreground its own runner. Restore only this
                // fresh owned Simulator's already-running game, without reset.
                await command(model.kind + '-restore-own-game-foreground', ['xcrun', 'simctl', 'launch', udid, recipe.appId]);
                await foreground(); report.accessibilityInteraction = true;
                await pause(90000); await foreground(); result.coldForegroundConfirmed = true;
                const cold = await rawShot(device, 'cold90', true); observation.coldCaptured = true;
                if (typeof getWindowRect !== 'function') fail('ACTUAL_WDA_POINT_SPACE_INTERFACE_MISSING');
                const screen = await execute('mobile: deviceScreenInfo', {}), windowRect = await getWindowRect();
                result.startProof = deriveTapPoint(cold.vision, screen, windowRect);
                await publish(); await foreground();
                await execute('mobile: tap', { ...result.startProof.screenPoint });
                observation.startTapped = true; result.visibleStartLabelTapped = true;
                await pause(20000); await foreground();
                await rawShot(device, 'after-start'); observation.afterStartCaptured = true;
                await command(model.kind + '-terminate', ['xcrun', 'simctl', 'terminate', udid, recipe.appId]);
                await stopConsole(coldConsole, result, 'cold'); coldConsole = null;
                warmConsole = await startProcess(model.kind + '-warm-own-game-console', ['xcrun', 'simctl', 'launch', '--console-pty', udid, recipe.appId], 900000);
                await pause(90000); await foreground(); result.warmForegroundConfirmed = true;
                await rawShot(device, 'warm90'); observation.warmCaptured = true;
                return observation;
              } catch (error) { result.observationError = { code: errorCode(error) }; await publish(); throw error; }
            },
          });
          result.appium = appium; result.actualAppium = appium.sessionCreated; report.actualAppium ||= appium.sessionCreated;
          report.accessibilityInteraction ||= appium.sessionCreated;
          if (appium.status !== 'completed') fail('BOUNDED_APPIUM_CAPTURE_FAILED');
          result.status = 'completed';
        }
      } catch (error) { result.error = { code: errorCode(error) }; await publish(); throw error; }
      finally {
        for (const [console, phase] of [[coldConsole, 'cold'], [warmConsole, 'warm']]) {
          try { await stopConsole(console, result, phase); }
          catch (error) { result.consoleCleanupError = { code: errorCode(error) }; result.status = 'failed'; }
        }
        await publish();
      }
      if (result.status !== 'completed') fail('OWN_GAME_CONSOLE_CLEANUP_FAILED');
      await command(model.kind + '-shutdown-after-capture', ['xcrun', 'simctl', 'shutdown', udid], { timeout: 60000 });
    }
    report.status = 'completed'; report.stage = 'complete';
  } catch (error) { report.error = { code: errorCode(error) }; }
  finally {
    for (const record of [...processes]) {
      try { await record.stop(); await record.result(); }
      catch { report.cleanup.push({ process: 'owned-child', status: 'unconfirmed' }); }
    }
    for (const device of owned) {
      const cleanup = { device: device.kind, udid: device.udid, status: 'unconfirmed' };
      try {
        const actual = await confirmOwned(device);
        if (actual.state !== 'Shutdown')
          await command('cleanup-shutdown-' + device.kind, ['xcrun', 'simctl', 'shutdown', device.udid], { allowFailure: true, timeout: 60000 });
        await command('cleanup-delete-' + device.kind, ['xcrun', 'simctl', 'delete', device.udid], { timeout: 60000 });
        cleanup.status = 'deleted';
      } catch (error) { cleanup.error = { code: errorCode(error) }; }
      report.cleanup.push(cleanup);
    }
    if (report.cleanup.some(item => item.status === 'unconfirmed')) {
      report.status = 'failed'; report.error ||= { code: 'OWNED_CLEANUP_UNCONFIRMED' };
    }
    try {
      const scratchTarget = await fs.realpath(scratch);
      if (!inside(runnerTemp, scratchTarget) || scratchTarget === runnerTemp || !path.basename(scratchTarget).startsWith('godot-bounded-capture-'))
        fail('PRIVATE_SCRATCH_CLEANUP_REFUSED');
      if (processes.size !== 0) fail('PRIVATE_SCRATCH_HAS_UNCONFIRMED_PROCESS');
      await fs.rm(scratchTarget, { recursive: true, force: true });
      report.cleanup.push({ temporaryDirectory: 'owned-scratch', status: 'removed' });
    } catch (error) {
      report.status = 'failed'; report.error ||= { code: errorCode(error) };
      report.cleanup.push({ temporaryDirectory: 'owned-scratch', status: 'unconfirmed', error: { code: errorCode(error) } });
    }
    await publish();
  }
  return report;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  try {
    if (args.length !== 5) fail('USAGE_NODE_SCRIPT_MODE_SOURCE_METADATA_VERIFIER_OUTPUT');
    const [mode, source, metadata, verifier, output] = args;
    const report = await captureNative({ mode, source, metadata, verifier, output });
    console.log(`Bounded native capture ${report.status}; manual visual review required; raw logs withheld.`);
    if (report.status !== 'completed') process.exitCode = 1;
  } catch (error) {
    console.error(`Bounded native capture stopped: ${errorCode(error)}; raw logs withheld.`);
    process.exitCode = 1;
  }
}
