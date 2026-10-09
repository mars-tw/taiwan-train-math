// Unsigned Simulator-only verification. Does not build, sign or upload an IPA.
import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { checkedAuthority, startOwnedSampleFeed, proveInteraction, createRunnerBootstrapGate } from './crack-interaction-proof.mjs';

const projects = { 'crackveil-vanguard': ['CrackveilVanguard', 'tw.mars.crackveilvanguard'] };
const [project, source, metadata, verifier, output, authorityFile] = process.argv.slice(2);
if(process.argv.slice(2).length!==6||project!=='crackveil-vanguard') throw new Error('Exact scoped Crack build2 arguments required');
const metadataBytes=await fs.readFile(metadata);
const authority=checkedAuthority(JSON.parse(await fs.readFile(authorityFile,'utf8')),JSON.parse(metadataBytes.toString('utf8')),crypto.createHash('sha256').update(metadataBytes).digest('hex'));
if(process.platform!=='darwin'||process.arch!=='x64'||!process.env.RUNNER_TEMP)throw new Error('Actual Intel Mac required');
const [name, appId] = projects[project];
const scripts = path.dirname(fileURLToPath(import.meta.url));
const scratch = await fs.mkdtemp(path.join(process.env.RUNNER_TEMP, 'godot-runtime-capture-'));
await fs.mkdir(output, { recursive: true });
const devices = [], consoles = [], results = [], feeds=[];
const sha = data => crypto.createHash('sha256').update(data).digest('hex');
const safeLines = raw => raw.split(/\r?\n/).filter(line => /error:|SCRIPT ERROR|OWN_GAME_|CAPTURE_|crash|failed/i.test(line)).slice(-25).map(line => line
  .replace(/https?:\/\/[^\s"'<>]+/g, '<url>')
  .replace(/\/(?:Users|private|var|Volumes)\/[^\s"'<>]+/g, '<path>')
  .replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, 500));

async function command(label, args, { timeout = 120000, allowFailure = false, observer=null } = {}) {
  const logPath = path.join(scratch, label + '.log');
  const log = createWriteStream(logPath, { flags: 'wx', mode: 0o600 });
  let count = 0, timedOut = false;
  const child = spawn(args[0], args.slice(1), { stdio: ['ignore', 'pipe', 'pipe'] });
  const tails={stdout:'',stderr:''};
  const append = (stream,data) => { count += data.length; if (count <= 20 * 1024 * 1024) log.write(data);
    if(observer){tails[stream]+=data.toString('utf8');let at;while((at=tails[stream].indexOf('\n'))>=0){const line=tails[stream].slice(0,at).replace(/\r$/,'');tails[stream]=tails[stream].slice(at+1);observer.line(line);}
      if(tails[stream].length>4096){observer.line('CRACK_QA_RUNNER_BOOTSTRAP invalid');tails[stream]='';}
      if(observer.error())child.kill('SIGKILL');}
  };
  child.stdout.on('data',data=>append('stdout',data));child.stderr.on('data',data=>append('stderr',data));
  const timer = setTimeout(() => { timedOut = true; child.kill('SIGKILL'); }, timeout);
  const code = await new Promise(resolve => { child.once('error', () => resolve(-1)); child.once('close', resolve); });
  clearTimeout(timer);
  await new Promise(resolve => log.end(resolve));
  const text = await fs.readFile(logPath, 'utf8');
  const bootstrapError=observer?await observer.finish():null;
  if (code !== 0 && !allowFailure) {
    await fs.writeFile(path.join(output, 'capture-command-failure.json'), JSON.stringify({ projectId: project, command: label, code, timedOut, diagnostics: safeLines(text), rawLogsUploaded: false }, null, 2));
    throw new Error('Unsigned capture command failed: ' + label);
  }
  return { code, timedOut, text, bootstrapError };
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
  const runtimes = inventory.runtimes.filter(r => r.isAvailable === true && !r.availabilityError && /^26\.2(?:\.0)?$/.test(r.version||'') && /^com\.apple\.CoreSimulator\.SimRuntime\.iOS-26-2(?:-0)?$/.test(r.identifier||''));
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
    const runnerNonce=crypto.randomBytes(16).toString('hex');
    const runner = path.join(scratch, kind + '-runner');
    await command(kind + '-generate-runner', ['python3', path.join(scripts, 'create-crack-interaction-project.py'), runner, project, kind, runnerNonce]);
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
    // Cosmetic only: an observed status_bar timeout must not prevent actual
    // install/launch/XCTest verification. Preserve the native bar if unavailable.
    const statusBar = await command(kind + '-statusbar', ['xcrun', 'simctl', 'status_bar', device, 'override', '--time', '9:41', '--batteryState', 'charged', '--batteryLevel', '100'], { timeout: 30000, allowFailure: true });
    await command(kind + '-install', ['xcrun', 'simctl', 'install', device, app], { timeout: 360000 });
    // The mirror is in this actual installed XCTest Runner's own data container.
    const runnerApp=path.join(scratch,kind+'-derived-tests/Build/Products/Debug-iphonesimulator/CaptureUITests-Runner.app');
    const runnerId=(await command(kind+'-runner-bundle-id',['plutil','-extract','CFBundleIdentifier','raw','-o','-',path.join(runnerApp,'Info.plist')])).text.trim();
    if(runnerId!=='tw.mars.capture.tests.xctrunner')throw new Error('Actual scoped XCTest runner identity required');
    // XCTest now owns Runner installation; no game exists running before framework initialization.
    let feed=null;
    const gate=createRunnerBootstrapGate({kind,nonce:runnerNonce,runnerId},async(b,active)=>{
      const deadline=Date.now()+90000;
      const budget=()=>{if(!active()||Date.now()>=deadline)throw new Error('BOOTSTRAP_NOT_CURRENT');return Math.max(1,Math.min(180000,deadline-Date.now()));};
      const actual=JSON.parse((await command(kind+'-bootstrap-current-sim',['xcrun','simctl','list','--json'],{timeout:budget()})).text);
      const own=(actual.devices?.[runtime.identifier]||[]).filter(d=>String(d.udid).toLowerCase()===device.toLowerCase()&&d.name==='Mars-Godot-Capture-'+project+'-'+kind&&d.deviceTypeIdentifier===model.identifier&&d.isAvailable===true);
      if(own.length!==1)throw new Error('BOOTSTRAP_OWN_SIM_UNCONFIRMED');
      const runnerData=(await command(kind+'-current-runner-container',['xcrun','simctl','get_app_container',device,runnerId,'data'],{timeout:budget()})).text.trim();
      if(!path.isAbsolute(runnerData)||!runnerData.toLowerCase().includes('/devices/'+device.toLowerCase()+'/'))throw new Error('CURRENT_RUNNER_SANDBOX_REQUIRED');
      const docs=path.join(runnerData,'Documents');await fs.mkdir(docs,{recursive:true});const mirror=path.join(await fs.realpath(docs),'crack-native-qa-mirror.json');
      if(!active()||sha(Buffer.from(mirror))!==b.mirrorPathSha256)throw new Error('CURRENT_RUNNER_DOC_SHA_DIFFERS');
      const appData=(await command(kind+'-current-game-container',['xcrun','simctl','get_app_container',device,appId,'data'],{timeout:budget()})).text.trim();
      if(!active()||!path.isAbsolute(appData)||!appData.toLowerCase().includes('/devices/'+device.toLowerCase()+'/'))throw new Error('CURRENT_GAME_SANDBOX_REQUIRED');
      feed=await startOwnedSampleFeed({container:appData,mirror,kind,authority,nonce:runnerNonce});
      if(!active()){await feed.stop();throw new Error('BOOTSTRAP_CHILD_NOT_CURRENT');}feeds.push(feed);
    });
    const resultPath = path.join(scratch, kind + '.xcresult');
    const test = await command(kind + '-xctest', ['xcodebuild', '-project', path.join(runner, 'Capture.xcodeproj'), '-scheme', 'Capture',
      '-destination', 'platform=iOS Simulator,id=' + device, '-derivedDataPath', path.join(scratch, kind + '-derived-tests'),
      '-resultBundlePath', resultPath, '-parallel-testing-enabled', 'NO', 'CODE_SIGNING_ALLOWED=NO', 'ARCHS=x86_64', 'ONLY_ACTIVE_ARCH=YES', '-only-testing:CaptureUITests/CaptureUITests/testNativeInteraction', 'test-without-building'], { timeout: 1500000, allowFailure: true, observer:gate });
    // Save this launch's full passive stream before any terminate/relaunch.
    const passive=feed?await feed.stop():{samples:[],error:test.bootstrapError||'CURRENT_GAME_FEED_MISSING',total:0,nonce:runnerNonce,fileRead:false,sampleFileSha256:null,physicalDeviceTested:false};
    const passiveFile=path.join(output,kind+'-session-passive-evidence.json');
    await fs.writeFile(passiveFile,JSON.stringify({projectId:project,appId,version:'1.0.0',build:2,pckSha256:authority.pckSha256,kind,...passive},null,2));
    if(test.code!==0||test.timedOut||passive.error||test.bootstrapError||passive.nonce!==runnerNonce){
      const safePassiveCode=typeof passive.error==='string'&&/^[A-Z0-9_]{1,100}$/.test(passive.error)?passive.error:passive.error?'PASSIVE_FAILURE_UNKNOWN':null;
      const failure={status:'NATIVE_INTERACTION_TEST_FAILED',projectId:project,appId,version:'1.0.0',build:2,pckSha256:authority.pckSha256,device:kind,
        command:kind+'-xctest',exitCode:Number.isInteger(test.code)?test.code:null,timedOut:test.timedOut===true,
        reason:test.bootstrapError|| (test.timedOut?'XCTEST_TIMED_OUT':test.code!==0?'XCTEST_EXIT_NONZERO':'PASSIVE_SAMPLE_FAILURE'),
        passiveFailureCode:safePassiveCode,passiveFileRead:passive.fileRead===true,
        passiveSampleCount:Number.isSafeInteger(passive.total)&&passive.total>=0&&passive.total<=30000?passive.total:null,
        safeTestDiagnostics:typeof test.text==='string'?safeLines(test.text):[],rawLogsIncluded:false,
        interactiveGameplayTested:false,nativeRuntimeReady:false,uiReleaseReady:false,physicalDeviceTested:false,storeQualified:false};
      try{await fs.writeFile(path.join(output,'capture-command-failure.json'),JSON.stringify(failure,null,2));}
      catch{console.error('SAFE_INTERACTION_FAILURE_RECEIPT_WRITE_FAILED');}
      throw new Error('Actual interaction failed; no warm fallback or second Start');
    }
    proveInteraction({testText:test.text,feed:passive,kind,authority,phase:'cold'});
    await command(kind+'-stop-saved-game-before-warm',['xcrun','simctl','terminate',device,appId],{timeout:180000});
    const warmPath=path.join(scratch,kind+'-warm.xcresult');
    const warm=await command(kind+'-warm-xctest',['xcodebuild','-project',path.join(runner,'Capture.xcodeproj'),'-scheme','Capture',
      '-destination','platform=iOS Simulator,id='+device,'-derivedDataPath',path.join(scratch,kind+'-derived-tests'),
      '-resultBundlePath',warmPath,'-parallel-testing-enabled','NO','CODE_SIGNING_ALLOWED=NO','ARCHS=x86_64','ONLY_ACTIVE_ARCH=YES',
      '-only-testing:CaptureUITests/CaptureUITests/testWarmMenu','test-without-building'],{timeout:600000,allowFailure:true});
    if(warm.code!==0||warm.timedOut)throw new Error('Actual warm observation failed');
    const interaction=proveInteraction({testText:test.text+'\n'+warm.text,feed:passive,kind,authority});
    test.text += '\n'+warm.text;
    const consoleText=''; // No prelaunch console; primary evidence remains current own app JSONL.
    const exported = path.join(scratch, kind + '-attachments');
    await fs.mkdir(exported);
    const exportResult = await command(kind + '-export-attachments', ['xcrun', 'xcresulttool', 'export', 'attachments', '--path', resultPath, '--output-path', exported], { allowFailure: true });
    const warmExported=path.join(scratch,kind+'-warm-attachments');await fs.mkdir(warmExported);
    const warmExport=await command(kind+'-export-warm-attachments',['xcrun','xcresulttool','export','attachments','--path',warmPath,'--output-path',warmExported],{allowFailure:true});
    if(warmExport.code!==0||exportResult.code!==0)throw new Error('Both native attachment exports required');
    const warmManifest=JSON.parse(await fs.readFile(path.join(warmExported,'manifest.json'),'utf8'));
    const remap=node=>{if(Array.isArray(node))return node.map(remap);if(!node||typeof node!=='object')return node;
      const o={...node};if(typeof o.exportedFileName==='string'){if(!/^[A-Za-z0-9_.-]+\.png$/i.test(o.exportedFileName))throw new Error('Warm attachment filename required');o.exportedFileName='warm-'+o.exportedFileName;}
      for(const k of Object.keys(o))if(typeof o[k]==='object')o[k]=remap(o[k]);return o;};
    for(const e of await fs.readdir(warmExported)){if(/^[A-Za-z0-9_.-]+\.png$/i.test(e))await fs.copyFile(path.join(warmExported,e),path.join(exported,'warm-'+e));}
    const mainManifest=JSON.parse(await fs.readFile(path.join(exported,'manifest.json'),'utf8'));await fs.writeFile(path.join(exported,'manifest.json'),JSON.stringify([mainManifest,remap(warmManifest)]));
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
        const rawMatch = human.match(new RegExp('^' + kind + '-(menu90|after-start|after-move|paused|resumed|relaunch90)-raw(?:[^A-Za-z0-9]|$)'));
        if (rawMatch && /^[A-Za-z0-9_.-]+\.png$/i.test(attachment.exportedFileName)) {
          const bytes = await fs.readFile(path.join(exported, attachment.exportedFileName));
          const file = kind + '-' + rawMatch[1] + '-raw.png';
          await fs.writeFile(path.join(output, 'raw-screenshots', file), bytes);
          rawShots.push({ file: 'raw-screenshots/' + file, sha256: sha(bytes), bytes: bytes.length, originalXCUIScreenshotPngRepresentation: true });
          continue;
        }
        const match = human.match(new RegExp('^' + kind + '-(menu90|after-start|after-move|paused|resumed|relaunch90)(?:[^A-Za-z0-9]|$)'));
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
        if (!new RegExp('^' + kind + '-(menu90|after-start|after-move|paused|resumed|relaunch90)$').test(data.stage) || fields.some(key => typeof data[key] !== 'number' || !Number.isFinite(data[key]))) return null;
        return Object.fromEntries(['stage', ...fields].map(key => [key, data[key]]));
      } catch { return null; }
    }).filter(Boolean);
    // IHDR is backing pixel storage, not displayed orientation. The actual
    // Seven screen is 1320x2868 with EXIF6 and a 956x440 landscape UIImage.
    // Verify that complete contract; preserve every original PNG pixel.
    const exifForImage = [1, 3, 8, 6, 2, 4, 5, 7];
    for (const shot of shots) {
      const stage = path.basename(shot.file, '.png');
      const g = geometry.find(item => item.stage === stage);
      const exif = g && exifForImage[g.imageOrientation];
      const quarterTurn = [5, 6, 7, 8].includes(exif);
      const semanticWidth = g && (quarterTurn ? g.cgHeight : g.cgWidth);
      const semanticHeight = g && (quarterTurn ? g.cgWidth : g.cgHeight);
      shot.encodedLandscapeFrame = shot.width > shot.height;
      shot.landscapeFrame = Boolean(g && exif && g.pngOrientation === exif && g.appX === 0 && g.appY === 0
        && g.appWidth > g.appHeight && g.imageScale > 0 && shot.width === g.cgWidth && shot.height === g.cgHeight
        && Math.abs(g.imageWidth - g.appWidth) < 0.01 && Math.abs(g.imageHeight - g.appHeight) < 0.01
        && Math.abs(semanticWidth - g.imageWidth * g.imageScale) < 1 && Math.abs(semanticHeight - g.imageHeight * g.imageScale) < 1);
      shot.displayOrientationVerifiedFromNativeMetadata = shot.landscapeFrame;
    }
    results.push({ device: kind, model: model.name, statusBarOverride: { code: statusBar.code, timedOut: statusBar.timedOut }, actualXCTestExit: test.code, timedOut: test.timedOut, screenshots: shots, rawScreenshots: rawShots, geometry,
      actualXCTestExecuted: /CAPTURE_TEST_METHOD_ENTERED=/.test(test.text), ownGameForegroundAtMenu90: /CAPTURE_MENU90_FOREGROUND=true/.test(test.text) ? true : /CAPTURE_MENU90_FOREGROUND=false/.test(test.text) ? false : null,
      ownGameConsoleDiagnostics: safeLines(consoleText), uiTestDiagnostics: safeLines(test.text),
      visibleStartLabelTapped:interaction.startActionCount===1,interaction,gameplaySceneRequiresVisualReview:true });
    await fs.writeFile(path.join(output, 'runtime-capture.json'), JSON.stringify({ projectId: project, appId, nativeVersion: '1.0.0', nativeBuild: 2, pckSha256:authority.pckSha256, sourceInputManifestSha256:authority.sourceInputManifestSha256,
      actualSimulator: true, actualXCTest: results.every(r => r.actualXCTestExecuted), runtime: runtime.version, runnerArchitecture: 'x86_64', sameVerifiedBuild2SourceUnchanged: false, sourceAfterVerificationPending: true,
      unsignedSimulatorLinkOnly: true, signedIpaRebuilt: false, signerSecretsUsed: false, screenshotResized: false,
      physicalDeviceTested: false, speakerOutputTested: false, storeUploadPerformed: false, results }, null, 2));
    await command(kind + '-shutdown', ['xcrun', 'simctl', 'shutdown', device]);
  }
  if (results.some(r => r.actualXCTestExit !== 0 || r.screenshots.length !== 6 || r.screenshots.some(s => !s.landscapeFrame))) throw new Error('Actual runtime capture failed; inspect public evidence before any store upload');
  await command('source-verify-after-interaction',['python3',verifier,'source','--root',source,'--metadata',metadata,'--project',project,'--output',path.join(output,'source-verification-after-interaction.json')]);
  const completedCapture = JSON.parse(await fs.readFile(path.join(output,'runtime-capture.json'),'utf8'));
  completedCapture.sameVerifiedBuild2SourceUnchanged = true;
  completedCapture.sourceAfterVerificationPending = false;
  await fs.writeFile(path.join(output,'runtime-capture.json'),JSON.stringify(completedCapture,null,2));
  await fs.writeFile(path.join(output,'interaction-observed.json'),JSON.stringify({status:'TWO_SIMULATOR_INPUT_STATE_OBSERVED',projectId:project,appId,version:'1.0.0',build:2,pckSha256:authority.pckSha256,devices:Object.fromEntries(results.map(r=>[r.device,r.interaction])),physicalDeviceTested:false,nativeRuntimeReady:false,uiReleaseReady:false,storeQualified:false},null,2));
  if(results.some(r=>r.interaction.touchMoveVerified!==true))throw new Error('ACTOR_SCENE_CONTINUITY_UNCONFIRMED');
  await fs.writeFile(path.join(output,'interaction-proof.json'),JSON.stringify({status:'TWO_SIMULATOR_REAL_INPUT_AND_STATE_VERIFIED',projectId:project,appId,version:'1.0.0',build:2,pckSha256:authority.pckSha256,sourceInputManifestSha256:authority.sourceInputManifestSha256,devices:Object.fromEntries(results.map(r=>[r.device,r.interaction])),physicalDeviceTested:false,nativeSimulatorInteractionVerified:true,appReviewPhysicalRecordingProvided:false,storeQualified:false},null,2));
} catch (error) {
  await fs.writeFile(path.join(output,'interaction-hold.json'),JSON.stringify({status:'ACTUAL_INTERACTION_UNCONFIRMED',projectId:project,build:2,nativeRuntimeReady:false,uiReleaseReady:false,physicalDeviceTested:false,storeQualified:false,reason:typeof error?.message==='string'&&/^[A-Za-z0-9 :;.\/-]{1,180}$/.test(error.message)?error.message:'NATIVE_INTERACTION_UNKNOWN'},null,2));
  console.error('Scoped Crack interaction stopped; diagnostics retained, no readiness claimed.');
  process.exitCode = 1;
} finally {
  for(const feed of feeds)await feed.stop().catch(()=>{});
  for (const consoleProcess of consoles) consoleProcess.kill('SIGTERM');
  for (const device of devices) {
    await command('cleanup-shutdown-' + device, ['xcrun', 'simctl', 'shutdown', device], { allowFailure: true, timeout: 60000 }).catch(() => {});
    await command('cleanup-delete-' + device, ['xcrun', 'simctl', 'delete', device], { allowFailure: true, timeout: 60000 }).catch(() => {});
  }
  const parent = path.resolve(process.env.RUNNER_TEMP), target = path.resolve(scratch);
  if (target.startsWith(parent + path.sep) && path.basename(target).startsWith('godot-runtime-capture-')) await fs.rm(target, { recursive: true, force: true });
}
