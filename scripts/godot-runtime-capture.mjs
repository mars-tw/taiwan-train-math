// Unsigned Simulator-only verification. Does not build, sign or upload an IPA.
import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const projects = { 'crackveil-vanguard': ['CrackveilVanguard', 'tw.mars.crackveilvanguard'],
  'seven-district-reckoning': ['SevenDistrict', 'tw.mars.sevendistrictreckoning'] };
const [project, source, metadata, verifier, output] = process.argv.slice(2);
if (!(project in projects) || process.platform !== 'darwin' || process.arch !== 'x64' || !process.env.RUNNER_TEMP) throw new Error('Explicit approved project and actual Intel Mac required');
const [name, appId] = projects[project];
const scripts = path.dirname(fileURLToPath(import.meta.url));
const scratch = await fs.mkdtemp(path.join(process.env.RUNNER_TEMP, 'godot-runtime-capture-'));
await fs.mkdir(output, { recursive: true });
const devices = [], consoles = [], results = [];
const sha = data => crypto.createHash('sha256').update(data).digest('hex');
const safeLines = raw => raw.split(/\r?\n/).filter(line => /error:|SCRIPT ERROR|OWN_GAME_|CAPTURE_|crash|failed/i.test(line)).slice(-25).map(line => line
  .replace(/https?:\/\/[^\s"'<>]+/g, '<url>')
  .replace(/\/(?:Users|private|var|Volumes)\/[^\s"'<>]+/g, '<path>')
  .replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, 500));

async function command(label, args, { timeout = 120000, allowFailure = false } = {}) {
  const logPath = path.join(scratch, label + '.log');
  const log = createWriteStream(logPath, { flags: 'wx', mode: 0o600 });
  let count = 0, timedOut = false;
  const child = spawn(args[0], args.slice(1), { stdio: ['ignore', 'pipe', 'pipe'] });
  const append = data => { count += data.length; if (count <= 20 * 1024 * 1024) log.write(data); };
  child.stdout.on('data', append); child.stderr.on('data', append);
  const timer = setTimeout(() => { timedOut = true; child.kill('SIGKILL'); }, timeout);
  const code = await new Promise(resolve => { child.once('error', () => resolve(-1)); child.once('close', resolve); });
  clearTimeout(timer);
  await new Promise(resolve => log.end(resolve));
  const text = await fs.readFile(logPath, 'utf8');
  if (code !== 0 && !allowFailure) {
    await fs.writeFile(path.join(output, 'capture-command-failure.json'), JSON.stringify({ projectId: project, command: label, code, timedOut, diagnostics: safeLines(text), rawLogsUploaded: false }, null, 2));
    throw new Error('Unsigned capture command failed: ' + label);
  }
  return { code, timedOut, text };
}

const rgbSource = `import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
let input = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
guard let source = CGImageSourceCreateWithURL(input as CFURL, nil), let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
let context = CGContext(data: nil, width: image.width, height: image.height, bitsPerComponent: 8, bytesPerRow: image.width*4,
space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { exit(2) }
context.draw(image, in: CGRect(x: 0, y: 0, width: CGFloat(image.width), height: CGFloat(image.height)))
guard let rgb = context.makeImage(), let destination = CGImageDestinationCreateWithURL(output as CFURL, UTType.png.identifier as CFString, 1, nil) else { exit(2) }
let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [String:Any]
let orientation = properties?[kCGImagePropertyOrientation as String]
let preserved: [String:Any] = orientation == nil ? [:] : [kCGImagePropertyOrientation as String: orientation!]
CGImageDestinationAddImage(destination, rgb, preserved as CFDictionary)
guard CGImageDestinationFinalize(destination) else { exit(2) }
`;

try {
  const xcode = await command('xcode-version', ['xcodebuild', '-version']);
  if (!/^Xcode 26\.3\s+Build version 17C529\s*$/.test(xcode.text.trim())) throw new Error('Exact approved Xcode required');
  await command('source-verify', ['python3', verifier, 'source', '--root', source, '--metadata', metadata, '--project', project, '--output', path.join(output, 'source-verification.json')]);
  const lib = path.join(source, name + '.xcframework/ios-arm64_x86_64-simulator/libgodot.a');
  const architecture = await command('actual-library-architecture', ['xcrun', 'lipo', '-archs', lib]);
  if (architecture.text.trim() !== 'x86_64') throw new Error('Verified source Simulator library must actually be x86_64');
  await command('unsigned-sim-link', ['xcodebuild', '-project', path.join(source, name + '.xcodeproj'), '-scheme', name,
    '-configuration', 'Debug', '-sdk', 'iphonesimulator', '-destination', 'generic/platform=iOS Simulator',
    '-derivedDataPath', path.join(scratch, 'derived-game'), 'CODE_SIGNING_ALLOWED=NO', 'ARCHS=x86_64', 'EXCLUDED_ARCHS=arm64', 'ONLY_ACTIVE_ARCH=NO', 'build'], { timeout: 2400000 });
  const app = path.join(scratch, 'derived-game/Build/Products/Debug-iphonesimulator', name + '.app');
  await command('unsigned-app-verify', ['python3', verifier, 'app', '--root', source, '--project', project, '--app', app, '--output', path.join(output, 'simulator-verification.json')]);
  const inventory = JSON.parse((await command('inventory', ['xcrun', 'simctl', 'list', '--json'])).text);
  const runtimes = inventory.runtimes.filter(r => r.isAvailable === true && r.identifier.startsWith('com.apple.CoreSimulator.SimRuntime.iOS-') && r.version.split('.')[0] === '26').sort((a, b) => b.version.localeCompare(a.version, undefined, { numeric: true }));
  const phone = inventory.devicetypes.filter(d => d.name === 'iPhone 17 Pro Max');
  const tablet = inventory.devicetypes.filter(d => d.name.startsWith('iPad Pro 13-inch (M4)')).sort((a, b) => Number(!a.name.includes('16GB')) - Number(!b.name.includes('16GB')));
  if (!runtimes.length || phone.length !== 1 || !tablet.length) throw new Error('Required actual runtime and models unavailable');
  const runtime = runtimes[0], parts = runtime.version.split('.').map(Number), encoded = parts[0] * 65536 + parts[1] * 256;
  const previous = new Set(Object.values(inventory.devices).flat().map(d => d.udid.toLowerCase()));
  await fs.writeFile(path.join(scratch, 'rgb.swift'), rgbSource);
  await fs.mkdir(path.join(output, 'screenshots'), { recursive: true });
  await fs.mkdir(path.join(output, 'raw-screenshots'), { recursive: true });
  for (const [kind, model] of [['iphone', phone[0]], ['ipad', tablet[0]]]) {
    if (!(model.minRuntimeVersion <= encoded && encoded <= model.maxRuntimeVersion)) throw new Error('Actual model/runtime mismatch');
    const runner = path.join(scratch, kind + '-runner');
    await command(kind + '-generate-runner', ['python3', path.join(scripts, 'create-godot-capture-project.py'), runner, project, kind]);
    // The observed Xcode formatter error must fail before spending time booting
    // a fresh device. This builds only the small independent UI-test runner.
    await command(kind + '-runner-build', ['xcodebuild', '-project', path.join(runner, 'Capture.xcodeproj'), '-scheme', 'Capture',
      '-sdk', 'iphonesimulator', '-destination', 'generic/platform=iOS Simulator', '-derivedDataPath', path.join(scratch, kind + '-derived-tests'),
      'CODE_SIGNING_ALLOWED=NO', 'ARCHS=x86_64', 'ONLY_ACTIVE_ARCH=YES', 'build-for-testing'], { timeout: 600000 });
    const device = (await command(kind + '-create', ['xcrun', 'simctl', 'create', 'Mars-Godot-Capture-' + project + '-' + kind, model.identifier, runtime.identifier])).text.trim();
    if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(device) || previous.has(device.toLowerCase())) throw new Error('Not a new owned Simulator');
    devices.push(device);
    await command(kind + '-boot', ['xcrun', 'simctl', 'boot', device], { timeout: 180000 });
    await command(kind + '-bootstatus', ['xcrun', 'simctl', 'bootstatus', device, '-b'], { timeout: 600000 });
    await command(kind + '-statusbar', ['xcrun', 'simctl', 'status_bar', device, 'override', '--time', '9:41', '--batteryState', 'charged', '--batteryLevel', '100']);
    await command(kind + '-install', ['xcrun', 'simctl', 'install', device, app], { timeout: 360000 });
    // The console is attached only to this fresh own game. No system log stream.
    const consoleLog = createWriteStream(path.join(scratch, kind + '-own-game-console.log'), { flags: 'wx', mode: 0o600 });
    const consoleProcess = spawn('xcrun', ['simctl', 'launch', '--terminate-running-process', '--console-pty', device, appId], { stdio: ['ignore', 'pipe', 'pipe'] });
    let consoleBytes = 0;
    const appendConsole = data => { consoleBytes += data.length; if (consoleBytes <= 10 * 1024 * 1024) consoleLog.write(data); };
    consoleProcess.stdout.on('data', appendConsole); consoleProcess.stderr.on('data', appendConsole);
    consoleProcess.on('error', () => {}); consoles.push(consoleProcess);
    const resultPath = path.join(scratch, kind + '.xcresult');
    const test = await command(kind + '-xctest', ['xcodebuild', '-project', path.join(runner, 'Capture.xcodeproj'), '-scheme', 'Capture',
      '-destination', 'platform=iOS Simulator,id=' + device, '-derivedDataPath', path.join(scratch, kind + '-derived-tests'),
      '-resultBundlePath', resultPath, '-parallel-testing-enabled', 'NO', 'CODE_SIGNING_ALLOWED=NO', 'ARCHS=x86_64', 'ONLY_ACTIVE_ARCH=YES', 'test'], { timeout: 1500000, allowFailure: true });
    consoleProcess.kill('SIGTERM');
    await Promise.race([new Promise(resolve => consoleProcess.once('close', resolve)), new Promise(resolve => setTimeout(resolve, 1000))]);
    consoleProcess.stdout.removeListener('data', appendConsole); consoleProcess.stderr.removeListener('data', appendConsole);
    await new Promise(resolve => consoleLog.end(resolve));
    const consoleText = await fs.readFile(path.join(scratch, kind + '-own-game-console.log'), 'utf8');
    const exported = path.join(scratch, kind + '-attachments');
    await fs.mkdir(exported);
    const exportResult = await command(kind + '-export-attachments', ['xcrun', 'xcresulttool', 'export', 'attachments', '--path', resultPath, '--output-path', exported], { allowFailure: true });
    const shots = [], rawShots = [];
    if (exportResult.code === 0) {
      const manifest = JSON.parse(await fs.readFile(path.join(exported, 'manifest.json'), 'utf8'));
      const walk = node => {
        if (Array.isArray(node)) return node.flatMap(walk);
        if (!node || typeof node !== 'object') return [];
        const own = typeof node.exportedFileName === 'string' ? [node] : [];
        return own.concat(Object.values(node).flatMap(walk));
      };
      for (const attachment of walk(manifest)) {
        const human = String(attachment.suggestedHumanReadableName || '');
        const rawMatch = human.match(new RegExp('^' + kind + '-(menu90|after-start|relaunch90)-raw(?:[^A-Za-z0-9]|$)'));
        if (rawMatch && /^[A-Za-z0-9_.-]+\.png$/i.test(attachment.exportedFileName)) {
          const bytes = await fs.readFile(path.join(exported, attachment.exportedFileName));
          const file = kind + '-' + rawMatch[1] + '-raw.png';
          await fs.writeFile(path.join(output, 'raw-screenshots', file), bytes);
          rawShots.push({ file: 'raw-screenshots/' + file, sha256: sha(bytes), bytes: bytes.length, originalXCUIScreenshotPngRepresentation: true });
          continue;
        }
        const match = human.match(new RegExp('^' + kind + '-(menu90|after-start|relaunch90)(?:[^A-Za-z0-9]|$)'));
        if (!match || !/^[A-Za-z0-9_.-]+\.png$/i.test(attachment.exportedFileName)) continue;
        const file = kind + '-' + match[1] + '.png';
        await command(kind + '-' + match[1] + '-rgb', ['xcrun', 'swift', path.join(scratch, 'rgb.swift'), path.join(exported, attachment.exportedFileName), path.join(output, 'screenshots', file)], { timeout: 180000 });
        const bytes = await fs.readFile(path.join(output, 'screenshots', file));
        if (bytes.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a' || bytes[25] !== 2) throw new Error('Actual capture is not RGB PNG');
        const width = bytes.readUInt32BE(16), height = bytes.readUInt32BE(20);
        const expected = kind === 'iphone' ? [1320, 2868] : [2064, 2752];
        if (!((width === expected[0] && height === expected[1]) || (height === expected[0] && width === expected[1]))) throw new Error('Actual model screenshot size mismatch; no resizing');
        shots.push({ file: 'screenshots/' + file, width, height, landscapeFrame: width > height, sha256: sha(bytes), rgbNoAlpha: true });
      }
    }
    const geometry = test.text.split(/\r?\n/).filter(line => line.startsWith('CAPTURE_GEOMETRY=')).map(line => {
      try {
        const data = JSON.parse(line.slice('CAPTURE_GEOMETRY='.length));
        const fields = ['deviceOrientation', 'imageOrientation', 'imageWidth', 'imageHeight', 'imageScale', 'cgWidth', 'cgHeight', 'pngOrientation', 'appX', 'appY', 'appWidth', 'appHeight'];
        if (!new RegExp('^' + kind + '-(menu90|after-start|relaunch90)$').test(data.stage) || fields.some(key => typeof data[key] !== 'number' || !Number.isFinite(data[key]))) return null;
        return Object.fromEntries(['stage', ...fields].map(key => [key, data[key]]));
      } catch { return null; }
    }).filter(Boolean);
    results.push({ device: kind, model: model.name, actualXCTestExit: test.code, timedOut: test.timedOut, screenshots: shots, rawScreenshots: rawShots, geometry,
      actualXCTestExecuted: /CAPTURE_TEST_METHOD_ENTERED=/.test(test.text), ownGameForegroundAtMenu90: /CAPTURE_MENU90_FOREGROUND=true/.test(test.text) ? true : /CAPTURE_MENU90_FOREGROUND=false/.test(test.text) ? false : null,
      ownGameConsoleDiagnostics: safeLines(consoleText), uiTestDiagnostics: safeLines(test.text),
      visibleStartLabelTapped: /CAPTURE_START_INPUT_METHOD=/.test(test.text), gameplaySceneRequiresVisualReview: true });
    await fs.writeFile(path.join(output, 'runtime-capture.json'), JSON.stringify({ projectId: project, appId, nativeVersion: '1.0.0', nativeBuild: 1,
      actualSimulator: true, actualXCTest: results.every(r => r.actualXCTestExecuted), runtime: runtime.version, runnerArchitecture: 'x86_64', sameOriginal47Files: true,
      unsignedSimulatorLinkOnly: true, signedIpaRebuilt: false, signerSecretsUsed: false, screenshotResized: false,
      physicalDeviceTested: false, speakerOutputTested: false, storeUploadPerformed: false, results }, null, 2));
    await command(kind + '-shutdown', ['xcrun', 'simctl', 'shutdown', device]);
  }
  if (results.some(r => r.actualXCTestExit !== 0 || r.screenshots.length !== 3 || r.screenshots.some(s => !s.landscapeFrame))) throw new Error('Actual runtime capture failed; inspect public evidence before any store upload');
} catch (error) {
  console.error('Godot unsigned runtime capture stopped; public evidence preserved, private raw logs withheld');
  process.exitCode = 1;
} finally {
  for (const consoleProcess of consoles) consoleProcess.kill('SIGTERM');
  for (const device of devices) {
    await command('cleanup-shutdown-' + device, ['xcrun', 'simctl', 'shutdown', device], { allowFailure: true, timeout: 60000 }).catch(() => {});
    await command('cleanup-delete-' + device, ['xcrun', 'simctl', 'delete', device], { allowFailure: true, timeout: 60000 }).catch(() => {});
  }
  const parent = path.resolve(process.env.RUNNER_TEMP), target = path.resolve(scratch);
  if (target.startsWith(parent + path.sep) && path.basename(target).startsWith('godot-runtime-capture-')) await fs.rm(target, { recursive: true, force: true });
}
