import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { chromium, webkit } from 'playwright';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { createPreviewServer } from '../scripts/serve.mjs';
import { resolve, extname } from 'node:path';
const out=process.env.TRAIN_MATH_STORE_EVIDENCE || 'docs/evidence/r3-store', shots='docs/store/screenshots';
let browser,server,base;
const audit=[];
before(async()=>{await mkdir(out,{recursive:true});await mkdir(shots,{recursive:true});server=await createPreviewServer({root:process.cwd()});await new Promise(r=>server.listen(0,'127.0.0.1',r));base=`http://127.0.0.1:${server.address().port}`;browser=await (process.env.TRAIN_MATH_REVIEW_BROWSER==='webkit'?webkit:chromium).launch({headless:true});});
after(async()=>{await browser?.close();await new Promise(r=>server.close(r));await writeFile(`${out}/reviewer-path.json`,JSON.stringify(audit,null,2));});
async function press(page,selector){const el=page.locator(selector).first();await el.scrollIntoViewIfNeeded();const r=await el.boundingBox();assert.ok(r&&r.width>=60&&r.height>=60,`${selector}: >=60px ${JSON.stringify(r)}`);await el.tap();}
async function guard(page){assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no page overflow');const small=await page.locator('button:not(:disabled),.dispatch-top a,.dispatch-entry a,.main-nav a,summary').evaluateAll(es=>es.filter(e=>e.getClientRects().length).map(e=>{const r=e.getBoundingClientRect();return {id:e.id,text:e.textContent.trim().slice(0,35),w:r.width,h:r.height};}).filter(r=>r.w<59.9||r.h<59.9));assert.deepEqual(small,[],'all rendered child controls >=60px');
 if(page.viewportSize().height<=360&&await page.locator('.dispatch-train').count()) {const train=await page.locator('.dispatch-train').boundingBox(),dock=await page.locator('.dispatch-controls').boundingBox();assert.ok(train.y+train.height<=dock.y+1,'quantity diagram stays above controls on the smallest landscape screen');}
}
const sizes=[['seCompact',320,568],['seCompactLandscape',568,320],['phoneLarge',440,956],['ipad11',834,1194],['ipad11Landscape',1194,834],['se',375,667],['seLandscape',667,375],['phone',430,932],['phoneLandscape',932,430],['ipad',768,1024],['ipadLandscape',1024,768],['ipad13',1032,1376],['ipad13Landscape',1376,1032],['desktopShort',1366,600],['laptop',1280,640],['storePhone',430,932],['storeTablet',1032,1376]];
for(const [name,width,height] of sizes)test(`${name}: cold launch, tutorial, three math goals, retry, pause, reopen, saved progress`,async()=>{
 const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:name==='storePhone'?3:name==='storeTablet'?2:1,hasTouch:true,isMobile:width<700,reducedMotion:'reduce'}),page=await context.newPage();const errors=[],external=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(new URL(r.url()).origin!==base)external.push(r.url());});
 const snap=async(label)=>{await page.screenshot({path:`${name.startsWith('store')?shots:out}/${name}-${label}.png`});};
 try {
  const started=Date.now();await page.goto(base,{waitUntil:'networkidle'});await guard(page);
  const first=await page.locator('#dispatch-open').boundingBox();assert.ok(first.y>=0&&first.y+first.height<=height,'signature entry on first screen');await snap('home');
  await press(page,'#dispatch-open');await page.locator('[data-dispatch="learn"]').waitFor();await press(page,'[data-dispatch="learn"]');await guard(page);await snap('load');
  await press(page,'[data-dispatch="check"]');assert.match(await page.locator('.dispatch-feedback').innerText(),/還需要 5 人/);
  for(let n=0;n<3;n++)await press(page,'[data-dispatch="add"]');
  await press(page,'#dispatch-pause');await page.reload();await press(page,'#dispatch-open');
  assert.match(await page.locator('.dispatch-equation').innerText(),/3 人上車了/);
  // A new page clears sessionStorage. The same context preserves only the passport's local state.
  const url=page.url();await page.close();const reopened=await context.newPage();
  reopened.on('pageerror',e=>errors.push(e.message));await reopened.goto(url,{waitUntil:'networkidle'});
  assert.match(await reopened.locator('.dispatch-equation').innerText(),/3 人上車了/);
  for(let n=0;n<2;n++)await press(reopened,'[data-dispatch="add"]');await press(reopened,'[data-dispatch="check"]');
  await guard(reopened);await press(reopened,'[data-dispatch="check"]');assert.match(await reopened.locator('.dispatch-feedback').innerText(),/總數仍是 5 人/);
  await press(reopened,'[data-dispatch="to-rear"]');await reopened.screenshot({path:`${name.startsWith('store')?shots:out}/${name}-split.png`});
  await press(reopened,'[data-dispatch="check"]');await press(reopened,'[data-dispatch="answer:3"]');assert.match(await reopened.locator('.dispatch-feedback').innerText(),/再選一次/);
  await press(reopened,'[data-dispatch="answer:4"]');await guard(reopened);
  assert.match(await reopened.locator('.dispatch-completed').innerText(),/已完成 1 班/);
  await reopened.screenshot({path:`${name.startsWith('store')?shots:out}/${name}-completed.png`});
  await press(reopened,'#dispatch-pause');await reopened.reload();assert.match(await reopened.locator('.dispatch-entry-record').innerText(),/已完成 1 班/);
  const elapsed=Date.now()-started;assert.ok(elapsed<180000,'reviewer sees completed signature within three minutes');assert.deepEqual(errors,[]);assert.deepEqual(external,[]);audit.push({name,width,height,status:'VERIFIED',coldStartToCompleted:true,reopenPersisted:true,wrongAnswerRetried:true,externalRequests:external,errors,elapsedMsConcurrentOnly:elapsed});
 }finally{await context.close();}
});
test('upper age lessons show every passenger and preserve quantities when returning from background',async()=>{
 const context=await browser.newContext({viewport:{width:768,height:1024},hasTouch:true}),page=await context.newPage();
 try {for(const [level,total] of [['medium',8],['large',14]]) {
  await page.goto(`${base}/#home`);await press(page,'#settings-open');await press(page,`[data-level="${level}"]`);await press(page,'[aria-label="關閉設定"]');
  // Completed lessons remain readable; explicitly start another with the new age setting.
  await press(page,'#dispatch-open');
  await page.locator('.dispatch-page').waitFor();
  if(await page.locator('[data-dispatch="start"]').count())await press(page,'[data-dispatch="start"]');
  await press(page,'[data-dispatch="learn"]');
  for(let i=0;i<total;i++)await press(page,'[data-dispatch="add"]');
  assert.equal(await page.locator('.front .occupied').count(),total);
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});
  assert.match(await page.locator('.dispatch-equation').innerText(),new RegExp(`${total} 人上車了`));
  await press(page,'[data-dispatch="check"]');await press(page,'[data-dispatch="to-rear"]');
  // First medium lesson leaves one passenger; the next lesson uses two, regardless of age.
  const wanted=Number((await page.locator('#dispatch-title').innerText()).match(/分 (\d+) 人/)[1]);for(let i=1;i<wanted;i++)await press(page,'[data-dispatch="to-rear"]');
  await press(page,'[data-dispatch="check"]');await press(page,`[data-dispatch="answer:${total-wanted}"]`);
  assert.ok(await page.locator('.dispatch-completed').isVisible());await press(page,'#dispatch-pause');
 }
 audit.push({upperAgeLessons:'VERIFIED',visiblePassengers:true,backgroundEventsSimulated:true});
 }finally{await context.close();}
});
test('parent gate blocks links, rejects a wrong answer, revokes on background and allows only an answered challenge',async()=>{
 const context=await browser.newContext({viewport:{width:768,height:1024},hasTouch:true}),page=await context.newPage();
 try {await page.goto(base);await press(page,'#about-open');await page.locator('#about-dialog a').first().click();assert.equal(context.pages().length,1);await page.locator('#web-parent-answer').fill('0');await press(page,'#web-parent-form button');assert.match(await page.locator('#web-parent-status').innerText(),/再確認/);
  await page.evaluate(()=>window.dispatchEvent(new Event('blur')));assert.equal(await page.locator('#web-parent-gate').evaluate(d=>d.open),false);
  await page.locator('#about-dialog a').first().click();const text=await page.locator('#web-parent-question').innerText();const [a,b]=text.match(/\d+/g).map(Number);await page.locator('#web-parent-answer').fill(String(a*b));
  // Record the permitted destination without opening an external window or making a network request.
  await page.evaluate(()=>{window.__opened=[];window.open=(url)=>window.__opened.push(url);});await press(page,'#web-parent-form button');assert.equal((await page.evaluate(()=>window.__opened)).length,1);audit.push({parentGate:'VERIFIED',wrongAnswerBlocked:true,backgroundRevoked:true,correctChallengeAllowed:true});
 }finally{await context.close();}
});
test('packaged first launch and signature work with network offline and local file responses only',async()=>{
 const context=await browser.newContext({viewport:{width:390,height:844},hasTouch:true,offline:true}),page=await context.newPage();const misses=[];
 const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.webmanifest':'application/manifest+json','.webp':'image/webp','.jpg':'image/jpeg','.png':'image/png','.svg':'image/svg+xml'};
 await context.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin!=='https://math.invalid'){misses.push(u.href);return route.abort();}let p=decodeURIComponent(u.pathname).slice(1)||'index.html';const file=resolve('dist-native',p);if(!file.startsWith(resolve('dist-native')+'/')&&!file.startsWith(resolve('dist-native')+'\\'))return route.abort();try{await route.fulfill({body:await readFile(file),contentType:mime[extname(file)]||'text/plain'});}catch{misses.push(p);await route.abort();}});
 try {await page.goto('https://math.invalid');await press(page,'#dispatch-open');await press(page,'[data-dispatch="learn"]');for(let i=0;i<5;i++)await press(page,'[data-dispatch="add"]');await press(page,'[data-dispatch="check"]');await press(page,'[data-dispatch="to-rear"]');await press(page,'[data-dispatch="check"]');await press(page,'[data-dispatch="answer:4"]');assert.match(await page.locator('.dispatch-completed').innerText(),/已完成 1 班/);assert.deepEqual(misses,[]);audit.push({packagedOffline:'VERIFIED',missingFiles:misses,nativeBridge:'Not exercised by a browser'});}finally{await context.close();}
});
