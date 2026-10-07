// Simulator QA transport only. The caller owns visible Start/HUD checks and artifacts.
// npm discovery: https://appium.io/docs/en/3.1/guides/managing-exts/#do-it-yourself-with-npm
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { createWriteStream } from 'node:fs';
import fs from 'node:fs/promises';
import { createServer } from 'node:net';
import path from 'node:path';

const APP_ID = 'tw.mars.sevendistrictreckoning';
const HTTP_TIMEOUT = 180000;
const READY_TIMEOUT = 30000;
const OBSERVATION_TIMEOUT = 600000;
const RESPONSE_LIMIT = 64 * 1024 * 1024;
const LOG_LIMIT = 20 * 1024 * 1024;
const OBSERVATIONS = ['coldCaptured', 'startTapped', 'afterStartCaptured', 'warmCaptured'];
const EXPECTED_VERSIONS = { appium: '3.1.0', 'appium-xcuitest-driver': '10.43.0', 'appium-webdriveragent': '11.4.0' };
const ERRORS = Object.freeze({
  INVALID_ARGUMENT: 'The bounded Appium session arguments are invalid.',
  RUNTIME_MISMATCH: 'The installed Appium runtime does not match the pinned project dependencies.',
  PRIVATE_LOG_FAILED: 'The private Appium log could not be retained.',
  SERVER_START_FAILED: 'The owned Appium server could not start.',
  SERVER_EXITED: 'The owned Appium server exited before the session finished.',
  SERVER_NOT_READY: 'The owned Appium server was not ready within 30 seconds.',
  HTTP_TIMEOUT: 'An Appium request exceeded its 180 second limit; it was not retried.',
  HTTP_ABORTED: 'An Appium request was cancelled during bounded cleanup; it was not retried.',
  HTTP_FAILED: 'An Appium request failed; it was not retried.',
  HTTP_REJECTED: 'Appium rejected a request; it was not retried.',
  INVALID_RESPONSE: 'Appium returned an invalid or oversized response.',
  SESSION_NOT_CREATED: 'Appium did not return a valid owned session identifier.',
  COMMAND_NOT_ALLOWED: 'The command is outside the bounded native QA interface.',
  SESSION_CLOSED: 'The bounded Appium command interface is closed.',
  COMMAND_IN_FLIGHT: 'Another bounded Appium command is still running.',
  INVALID_SCREENSHOT: 'Appium did not return a complete lossless PNG screenshot.',
  OBSERVATION_FAILED: 'The visible observation callback failed.',
  OBSERVATION_TIMEOUT: 'The visible observation callback exceeded its bounded time limit.',
  OBSERVATION_INCOMPLETE: 'The visible observation callback did not confirm all four capture actions.',
  CLEANUP_FAILED: 'Cleanup of the owned Appium session or server was not confirmed.',
  LOCAL_PREPARATION_FAILED: 'The local Appium session preparation failed.',
});
class SessionError extends Error {
  constructor(code) { super(ERRORS[code]); this.name = 'BoundedAppiumError'; this.code = code; }
}
const fail = code => { throw new SessionError(code); };
const safeError = error => {
  const code = error instanceof SessionError && Object.hasOwn(ERRORS, error.code) ? error.code : 'LOCAL_PREPARATION_FAILED';
  return { code, summary: ERRORS[code] };
};
const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const inside = (parent, target) => {
  const relative = path.relative(parent, target);
  return relative === '' || (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative));
};

async function reservePorts(count) {
  const reservations = [];
  try {
    for (let index = 0; index < count; index++) {
      const server = createServer();
      await new Promise((resolve, reject) => {
        server.once('error', reject);
        server.listen({ host: '127.0.0.1', port: 0, exclusive: true }, resolve);
      });
      reservations.push({ server, port: server.address().port });
    }
    return reservations.map(item => item.port);
  } finally {
    await Promise.all(reservations.map(({ server }) => new Promise(resolve => server.close(resolve))));
  }
}

async function pinnedRuntime(appiumBin) {
  if (typeof appiumBin !== 'string' || !path.isAbsolute(appiumBin)) fail('INVALID_ARGUMENT');
  const runtime = path.dirname(path.dirname(path.dirname(appiumBin)));
  if (path.resolve(appiumBin) !== path.join(runtime, 'node_modules', 'appium', 'index.js')) fail('RUNTIME_MISMATCH');
  try {
    const manifest = JSON.parse(await fs.readFile(path.join(runtime, 'package.json'), 'utf8'));
    for (const [name, version] of Object.entries(EXPECTED_VERSIONS)) {
      if (manifest.dependencies?.[name] !== version) fail('RUNTIME_MISMATCH');
      const installed = JSON.parse(await fs.readFile(path.join(runtime, 'node_modules', name, 'package.json'), 'utf8'));
      if (installed.name !== name || installed.version !== version) fail('RUNTIME_MISMATCH');
    }
    await fs.access(appiumBin);
    return runtime;
  } catch { fail('RUNTIME_MISMATCH'); }
}

function checkPng(value) {
  if (typeof value !== 'string' || !value.length || value.length > RESPONSE_LIMIT
    || value.length % 4 !== 0 || !/^[A-Za-z0-9+/]+={0,2}$/.test(value)) fail('INVALID_SCREENSHOT');
  const bytes = Buffer.from(value, 'base64');
  if (bytes.toString('base64') !== value || bytes.length < 45
    || bytes.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a'
    || bytes.readUInt32BE(8) !== 13 || bytes.toString('ascii', 12, 16) !== 'IHDR'
    || bytes.readUInt32BE(16) < 1 || bytes.readUInt32BE(20) < 1
    || bytes.readUInt32BE(16) > 20000 || bytes.readUInt32BE(20) > 20000
    || bytes.subarray(-12).toString('hex') !== '0000000049454e44ae426082') fail('INVALID_SCREENSHOT');
  return value;
}

function checkCommand(script, args) {
  if (!args || typeof args !== 'object' || Array.isArray(args) || Object.getPrototypeOf(args) !== Object.prototype)
    fail('COMMAND_NOT_ALLOWED');
  const keys = Object.keys(args);
  if (script === 'mobile: tap') {
    if (keys.some(key => !['x', 'y'].includes(key)) || keys.length !== 2
      || !Number.isFinite(args.x) || !Number.isFinite(args.y) || args.x < 0 || args.y < 0
      || args.x > 20000 || args.y > 20000) fail('COMMAND_NOT_ALLOWED');
  } else if (script === 'mobile: activeAppInfo' || script === 'mobile: deviceScreenInfo') {
    if (keys.length !== 0) fail('COMMAND_NOT_ALLOWED');
  } else if (script === 'mobile: queryAppState') {
    if (keys.length !== 1 || args.bundleId !== APP_ID) fail('COMMAND_NOT_ALLOWED');
  } else fail('COMMAND_NOT_ALLOWED');
}

/**
 * Start one owned localhost Appium server and one session for an already-running
 * Seven Simulator. Returns a safe report; operational failures do not expose raw
 * exceptions. observeStart({execute, getScreenshot, getWindowRect, sessionId}) writes its own
 * artifacts and returns exactly the four observation booleans. No result implies
 * a content-quality pass. Callers retain ownership of Simulator lifecycle cleanup.
 */
export async function runAppiumSession({ appiumBin, udid, bundleId, model, platformVersion, output, scratch, observeStart } = {}) {
  const report = { status: 'failed', stage: 'prepare', sessionCreated: false,
    observation: Object.fromEntries(OBSERVATIONS.map(key => [key, false])),
    cleanup: { session: 'not-created', server: 'not-started' }, rawLogsUploaded: false };
  let child, sessionId, endpoint, log, logFailed = false, logClosed = false;
  let spawnedError = false, childClosed = false, commandOpen = false, commandBusy = false, commandsFailed = false;
  let sessionAttempted = false, pendingChildClose;
  const controllers = new Set();

  async function request(method, suffix, payload, outerSignal) {
    // All routes are constructed here. No caller-controlled URL or redirect is accepted.
    const url = new URL(endpoint + suffix);
    if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || url.username || url.password)
      fail('COMMAND_NOT_ALLOWED');
    const controller = new AbortController();
    controllers.add(controller);
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, HTTP_TIMEOUT);
    try {
      const response = await fetch(url, { method, redirect: 'error',
        signal: outerSignal ? AbortSignal.any([controller.signal, outerSignal]) : controller.signal,
        headers: { 'content-type': 'application/json', accept: 'application/json' },
        ...(payload === undefined ? {} : { body: JSON.stringify(payload) }) });
      const reader = response.body?.getReader();
      if (!reader) fail('INVALID_RESPONSE');
      const chunks = []; let size = 0;
      try {
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > RESPONSE_LIMIT) { controller.abort(); fail('INVALID_RESPONSE'); }
          chunks.push(value);
        }
      } finally { reader.releaseLock(); }
      let data;
      try { data = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
      catch { fail('INVALID_RESPONSE'); }
      if (!response.ok || data?.value?.error) fail('HTTP_REJECTED');
      if (!data || !Object.hasOwn(data, 'value')) fail('INVALID_RESPONSE');
      return data.value;
    } catch (error) {
      if (error instanceof SessionError) throw error;
      if (timedOut) fail('HTTP_TIMEOUT');
      if (controller.signal.aborted || outerSignal?.aborted) fail('HTTP_ABORTED');
      fail('HTTP_FAILED');
    } finally { clearTimeout(timer); controllers.delete(controller); }
  }

  async function command(action) {
    if (!commandOpen || commandsFailed || childClosed) fail('SESSION_CLOSED');
    if (commandBusy) fail('COMMAND_IN_FLIGHT');
    commandBusy = true;
    try { return await action(); }
    catch (error) { commandsFailed = true; throw error; }
    finally { commandBusy = false; }
  }

  async function waitForChildClose(milliseconds) {
    if (childClosed) return;
    let timer;
    try { await Promise.race([pendingChildClose, new Promise(resolve => { timer = setTimeout(resolve, milliseconds); })]); }
    finally { clearTimeout(timer); }
  }

  try {
    if (bundleId !== APP_ID || typeof udid !== 'string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(udid)
      || typeof model !== 'string' || !/^(?:iPhone|iPad) [A-Za-z0-9 ()+.,-]{1,100}$/.test(model)
      || typeof platformVersion !== 'string' || !/^\d{1,2}(?:\.\d{1,2}){0,2}$/.test(platformVersion)
      || typeof observeStart !== 'function' || typeof output !== 'string' || typeof scratch !== 'string'
      || !path.isAbsolute(output) || !path.isAbsolute(scratch)) fail('INVALID_ARGUMENT');
    const runtime = await pinnedRuntime(appiumBin);
    await fs.mkdir(scratch, { recursive: true, mode: 0o700 });
    const [outputRoot, scratchRoot] = await Promise.all([fs.realpath(output), fs.realpath(scratch)]);
    if (inside(outputRoot, scratchRoot) || inside(scratchRoot, outputRoot)) fail('INVALID_ARGUMENT');
    const privateDirectory = await fs.mkdtemp(path.join(scratchRoot, 'appium-session-'));
    await fs.chmod(privateDirectory, 0o700);
    const config = path.join(privateDirectory, 'server-config.json');
    await fs.writeFile(config, JSON.stringify({ server: { 'relaxed-security': false, 'allow-insecure': [],
      'allow-cors': false, 'session-override': false, 'use-plugins': [] } }), { flag: 'wx', mode: 0o600 });
    log = createWriteStream(path.join(privateDirectory, 'server-and-wda-raw.log'), { flags: 'wx', mode: 0o600 });
    log.on('error', () => { logFailed = true; });
    try { await new Promise((resolve, reject) => { log.once('open', resolve); log.once('error', reject); }); }
    catch { fail('PRIVATE_LOG_FAILED'); }
    const [serverPort, wdaPort, mjpegPort] = await reservePorts(3);
    const basePath = '/bounded-' + randomUUID();
    endpoint = `http://127.0.0.1:${serverPort}${basePath}`;
    const env = { ...process.env, APPIUM_TMP_DIR: privateDirectory, TMPDIR: privateDirectory };
    delete env.APPIUM_HOME; // An explicit APPIUM_HOME disables npm-project discovery.
    report.stage = 'server-start';
    child = spawn(process.execPath, [appiumBin, 'server', '--config', config, '--address', '127.0.0.1',
      '--port', String(serverPort), '--base-path', basePath, '--use-drivers', 'xcuitest',
      '--tmp', privateDirectory, '--log-level', 'info', '--log-no-colors'],
    { cwd: runtime, env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
    let logBytes = 0;
    const append = chunk => {
      if (logFailed || logClosed || logBytes >= LOG_LIMIT) return;
      const retained = chunk.subarray(0, LOG_LIMIT - logBytes);
      logBytes += retained.length;
      log.write(retained);
    };
    child.stdout.on('data', append); child.stderr.on('data', append);
    child.once('error', () => { spawnedError = true; });
    pendingChildClose = new Promise(resolve => child.once('close', () => { childClosed = true; resolve(); }));

    report.stage = 'server-ready';
    const readyController = new AbortController();
    const readyTimer = setTimeout(() => readyController.abort(), READY_TIMEOUT);
    const readyDeadline = performance.now() + READY_TIMEOUT;
    let ready = false;
    try {
      while (performance.now() < readyDeadline) {
        if (spawnedError) fail('SERVER_START_FAILED');
        if (childClosed) fail('SERVER_EXITED');
        try {
          const status = await request('GET', '/status', undefined, readyController.signal);
          if (!childClosed && status?.ready === true && status?.build?.version === EXPECTED_VERSIONS.appium) { ready = true; break; }
        } catch (error) {
          if (readyController.signal.aborted) break;
          if (error.code !== 'HTTP_FAILED') throw error;
        }
        await pause(Math.min(1000, Math.max(0, readyDeadline - performance.now())));
      }
    } finally { clearTimeout(readyTimer); }
    if (!ready) fail('SERVER_NOT_READY');
    if (logFailed) fail('PRIVATE_LOG_FAILED');

    report.stage = 'session-create';
    sessionAttempted = true;
    // v10.43.0 driver.ts uses `wdaStartupRetries || 2` on Simulator: 1 means
    // one attempt, while 0 restores two attempts and therefore permits a retry.
    const capabilities = { platformName: 'iOS', 'appium:automationName': 'XCUITest',
      'appium:udid': udid, 'appium:deviceName': model, 'appium:platformVersion': platformVersion,
      'appium:bundleId': APP_ID, 'appium:noReset': true, 'appium:fullReset': false,
      'appium:autoLaunch': false, 'appium:forceAppLaunch': false, 'appium:shouldTerminateApp': false,
      'appium:waitForIdleTimeout': 0, 'appium:wdaStartupRetries': 1,
      'appium:wdaLaunchTimeout': HTTP_TIMEOUT, 'appium:wdaConnectionTimeout': HTTP_TIMEOUT,
      'appium:screenshotQuality': 0, 'appium:printPageSourceOnFindFailure': false,
      'appium:skipLogCapture': true, 'appium:showXcodeLog': true,
      'appium:derivedDataPath': path.join(privateDirectory, 'wda-derived'),
      'appium:wdaBaseUrl': 'http://127.0.0.1', 'appium:wdaBindingIP': '127.0.0.1',
      'appium:wdaLocalPort': wdaPort, 'appium:wdaRemotePort': wdaPort,
      'appium:mjpegServerPort': mjpegPort, 'appium:shutdownOtherSimulators': false,
      'appium:enforceFreshSimulatorCreation': false, 'appium:newCommandTimeout': 660 };
    const created = await request('POST', '/session', { capabilities: { alwaysMatch: capabilities, firstMatch: [{}] } });
    if (typeof created?.sessionId !== 'string' || !/^[A-Za-z0-9-]{1,128}$/.test(created.sessionId)) fail('SESSION_NOT_CREATED');
    sessionId = created.sessionId;
    report.sessionCreated = true;
    report.cleanup.session = 'pending';
    commandOpen = true;
    report.stage = 'observation';
    const execute = (script, args = {}) => command(async () => {
      checkCommand(script, args);
      return await request('POST', `/session/${sessionId}/execute/sync`, { script, args: [args] });
    });
    const getScreenshot = () => command(async () => checkPng(await request('GET', `/session/${sessionId}/screenshot`)));
    const getWindowRect = () => command(async () => {
      const value = await request('GET', `/session/${sessionId}/window/rect`);
      if (!value || !['x', 'y', 'width', 'height'].every(key => Number.isFinite(value[key]))
        || value.x < 0 || value.y < 0 || value.width <= 0 || value.height <= 0
        || value.width > 20000 || value.height > 20000) fail('INVALID_RESPONSE');
      return { x: value.x, y: value.y, width: value.width, height: value.height };
    });
    let observationTimer;
    try {
      const observation = await Promise.race([
        Promise.resolve().then(() => observeStart({ execute, getScreenshot, getWindowRect, sessionId })),
        new Promise((_, reject) => { observationTimer = setTimeout(() => reject(new SessionError('OBSERVATION_TIMEOUT')), OBSERVATION_TIMEOUT); }),
        pendingChildClose.then(() => { fail('SERVER_EXITED'); }),
      ]);
      for (const key of OBSERVATIONS) report.observation[key] = observation?.[key] === true;
    } catch (error) {
      if (error instanceof SessionError) throw error;
      fail('OBSERVATION_FAILED');
    } finally { clearTimeout(observationTimer); }
    if (commandsFailed || logFailed) fail(logFailed ? 'PRIVATE_LOG_FAILED' : 'OBSERVATION_FAILED');
    if (!OBSERVATIONS.every(key => report.observation[key])) fail('OBSERVATION_INCOMPLETE');
    report.status = 'completed';
    report.stage = 'complete';
  } catch (error) { report.error = safeError(error); }
  finally {
    commandOpen = false;
    for (const controller of controllers) controller.abort();
    if (sessionId) {
      try { await request('DELETE', `/session/${sessionId}`); report.cleanup.session = 'deleted'; }
      catch (error) { report.cleanup.session = 'unconfirmed'; report.cleanup.sessionError = safeError(error); }
    } else if (sessionAttempted) report.cleanup.session = 'unconfirmed';
    if (child) {
      try {
        if (!childClosed) child.kill('SIGTERM');
        await waitForChildClose(5000);
        if (!childClosed) { child.kill('SIGKILL'); await waitForChildClose(5000); }
        report.cleanup.server = childClosed ? 'stopped' : 'unconfirmed';
      } catch { report.cleanup.server = 'unconfirmed'; }
    }
    if (log) {
      logClosed = true;
      if (!log.destroyed && !log.writableFinished) await new Promise(resolve => {
        log.once('finish', resolve); log.once('error', resolve); log.end();
      });
      if (logFailed && !report.error) report.error = safeError(new SessionError('PRIVATE_LOG_FAILED'));
    }
    if ((report.cleanup.session === 'unconfirmed' || report.cleanup.server === 'unconfirmed') && !report.error) {
      report.stage = 'cleanup';
      report.error = safeError(new SessionError('CLEANUP_FAILED'));
    }
    if (report.error) report.status = 'failed';
  }
  return report;
}
