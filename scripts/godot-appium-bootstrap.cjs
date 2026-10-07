// Same Node process; static diagnostic stages only, original loader/error preserved.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const originalLoad = Module._load;
const entry = path.resolve(process.argv[1] || '');
const main = path.join(path.dirname(entry), 'build/lib/main.js');
const started = Date.now(), seen = new Set(); let emitted = 0;
function note(stage, role) {
  try {
    const key = stage + ':' + role;
    if (seen.has(key) || emitted >= 56) return;
    seen.add(key); emitted++;
    fs.writeSync(2, 'OWN_NODE_BOOTSTRAP ' + JSON.stringify({stage,role,elapsedMs:Date.now()-started}) + '\n');
  } catch { /* An observer failure never changes the original loader result. */ }
}
function selected(request, parent, isMain) {
  try {
    if (isMain && path.resolve(request) === entry) return 'entry';
    if (parent?.filename === entry) return request === 'asyncbox' ? 'entry-asyncbox' : request === './build/lib/main.js' ? 'appium-main' : null;
    if (parent?.filename === main) return ({'./logsink':'main-logsink','./logger':'main-logger','@appium/base-driver':'main-base-driver',
      '@appium/support':'main-support','./extension':'main-extension','./config':'main-config','./config-file':'main-config-file','./cli/parser':'main-parser'})[request] || null;
  } catch { }
  return null;
}
note('entered','preload');
Module._load = function(request,parent,isMain) {
  const role = selected(request,parent,isMain);
  if (role) note('import-begin',role);
  let returned = false;
  try { const value = Reflect.apply(originalLoad,this,arguments); returned = true; return value; }
  finally {
    if (role) note(returned ? 'import-end' : 'import-throw',role);
    if (isMain) Module._load = originalLoad;
  }
};
