import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';
import { createPreviewServer } from '../scripts/serve.mjs';
import { readTripSession, TRIP_SESSION_KEY } from '../src/trip-session.js';
import { defaults, allowedGames } from '../src/engine.js';
import { fieldMission } from '../src/fieldbook.js';
const {trains}=JSON.parse(readFileSync(new URL('../data/trains.json',import.meta.url),'utf8'));
const out='docs/evidence/r2-mobile';
const sizes=[['portrait',390,844],['landscape',844,390],['desktopShort',1366,600],['laptop',1280,640]];
let browser,server,base;
const audits=[];
before(async()=>{
  await mkdir(out,{recursive:true});server=await createPreviewServer({root:process.cwd()});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));base=`http://127.0.0.1:${server.address().port}`;
  browser=await chromium.launch({headless:true});
});
after(async()=>{ await browser?.close();await new Promise(r=>server.close(r));await writeFile(`${out}/e2e-audit.json`,JSON.stringify(audits,null,2)); });
async function session(page) {
  const raw=await page.evaluate(key=>sessionStorage.getItem(key),TRIP_SESSION_KEY);
  const trip=readTripSession({getItem:()=>raw},{trains});assert.ok(trip,'valid live session');return trip;
}
test('all 36 mission cards launch the matching age game through the real menu',async()=>{
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,reducedMotion:'reduce'});
  const page=await context.newPage();let goals=0;
  try {
    await page.goto(`${base}/#playroom`);
    for(const level of ['small','medium','large'])for(let i=0;i<12;i++) {
      await page.evaluate(p=>{localStorage.setItem('taiwan-train-math.v1',JSON.stringify(p));sessionStorage.clear();},{...defaults(),level,fieldbook:{small:0,medium:0,large:0,[level]:i}});
      await page.goto(`${base}/#playroom`);await page.reload();await tap(page,'[data-fieldbook]');
      await page.locator('#trip-exit').waitFor();const trip=await session(page);
      assert.equal(trip.meta.level,level);assert.equal(trip.meta.practice,fieldMission(level,i).game);goals++;
      await tap(page,'#trip-exit');
    }
    assert.equal(goals,36);audits.push({allMissionMenuLaunches:goals});
  }finally{await context.close();}
});
async function target(page,selector) {
  const control=page.locator(selector).first();
  for(let attempt=0;attempt<3;attempt++) {
    try {await control.scrollIntoViewIfNeeded();break;}
    catch(error) {if(attempt===2||!error.message.includes('not attached'))throw error;await page.waitForLoadState('networkidle');}
  }
  const result=await control.evaluate(el=>{
    const r=el.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
    // Measure actual text; decorative carriage wheels intentionally extend below buttons.
    const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);let node,clipped=false;
    while((node=walker.nextNode()))if(node.textContent.trim()) {
      const range=document.createRange();range.selectNodeContents(node);
      for(const text of range.getClientRects())if(text.left<r.left-2||text.right>r.right+2||text.top<r.top-2||text.bottom>r.bottom+2)clipped=true;
    }
    return {w:r.width,h:r.height,top:r.top,bottom:r.bottom,view:innerHeight,hit:!!hit&&(hit===el||el.contains(hit)),clipped,text:el.textContent.trim()};
  });
  assert.ok(result.w>=44&&result.h>=44,`${selector} is at least 44px: ${JSON.stringify(result)}`);
  assert.ok(result.top>=-1&&result.bottom<=result.view+1&&result.hit,`${selector} visible and unblocked: ${JSON.stringify(result)}`);
  assert.equal(result.clipped,false,`${selector} text is not clipped`);
  return control;
}
async function press(page,control) { if(page.viewportSize().width<1000)await control.tap();else await control.click(); }
async function tap(page,selector) { await press(page,await target(page,selector)); }
async function guard(page) {
  await target(page,'#trip-exit');
  const small=await page.locator('#game-stage button:not(:disabled),#game-actions button:not(:disabled)').evaluateAll(elements=>elements.filter(el=>el.getClientRects().length).map(el=>{const r=el.getBoundingClientRect();return {label:el.getAttribute('aria-label')||el.id,w:r.width,h:r.height};}).filter(r=>r.w<44||r.h<44));
  assert.deepEqual(small,[],'all active activity and dock targets meet 44px');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal overflow');
  const buttons=page.locator('#game-actions button:not(:disabled)');
  for(let i=0;i<await buttons.count();i++) {const id=await buttons.nth(i).getAttribute('id');if(id)await target(page,`#${id}`);}
}
async function solveBasic(page) {
  const trip=await session(page),q=trip.questions[trip.index];
  if(q.game==='order') {for(const value of q.answer)await tap(page,`[data-order="${value}"]`);await tap(page,'#order-submit');}
  else await tap(page,`[data-answer="${q.answer}"]`);
  await page.locator('#question-next').waitFor();await guard(page);
}
for(const [name,width,height] of sizes) {
  test(`${name}: touch complete a chapter, pause/reload, claim gift, persist stamp and unlock next goal`,async()=>{
    const context=await browser.newContext({viewport:{width,height},isMobile:width<1000,hasTouch:width<1000,reducedMotion:'reduce'});
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    try {
      await page.goto(`${base}/#playroom`,{waitUntil:'networkidle'});
      const launch=await page.locator('[data-fieldbook]').boundingBox();assert.ok(launch&&launch.y>=0&&launch.y+launch.height<=height,'mission launch is on the first screen');
      await target(page,'[data-fieldbook]');await page.screenshot({path:`${out}/after-${name}-mission.png`});
      await tap(page,'[data-fieldbook]');await page.locator('#trip-exit').waitFor();
      const original=(await session(page)).meta.seed;
      await solveBasic(page);await tap(page,'#question-next');
      await page.evaluate(()=>scrollTo(0,document.body.scrollHeight));
      // Pause must work after scrolling through a long activity, without scrollIntoView assistance.
      const exit=await page.locator('#trip-exit').boundingBox();assert.ok(exit.y>=0&&exit.y+exit.height<=height);
      await press(page,page.locator('#trip-exit'));await page.reload();await tap(page,'#journey-resume');
      assert.equal((await session(page)).meta.seed,original);assert.equal((await session(page)).index,1);
      for(let mission=0;mission<3;mission++) {
        while(await page.locator('#trip-exit').count()) {await solveBasic(page);await tap(page,'#question-next');}
        assert.match(await page.locator('.fieldbook-result').innerText(),new RegExp(`${mission+1}／12`));
        if(mission<2) await tap(page,'.fieldbook-result [data-fieldbook]');
      }
      assert.match(await page.locator('.fieldbook-result').innerText(),/新收藏章：月台小幫手/);
      await page.screenshot({path:`${out}/after-${name}-chapter-reward.png`});
      // Existing gift credits must remain reachable and claim only one credit.
      await tap(page,'#gift-open');
      const giftChoice=page.locator('[data-gift-choice]').first();
      await press(page,giftChoice);
      assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('taiwan-train-math.v1')).giftCredits),2);
      await page.goto(`${base}/#stamps`);await page.reload();
      await page.locator('.field-stamp.earned').waitFor();
      assert.equal(await page.locator('.field-stamp.earned').count(),1);
      assert.match(await page.locator('.fieldbook-count').innerText(),/3／12/);
      await page.screenshot({path:`${out}/after-${name}-passport.png`});
      await tap(page,'[data-fieldbook]');assert.equal((await session(page)).meta.practice,'cargo');
      assert.deepEqual(errors,[]);audits.push({name,chapterCompleted:true,restoredSameSeed:true,stampReadback:true,errors});
    } finally {await context.close();}
  });
  test(`${name}: all age-appropriate activities retain reachable controls and pause on a scrolled page`,async()=>{
    const context=await browser.newContext({viewport:{width,height},isMobile:width<1000,hasTouch:width<1000,reducedMotion:'reduce'});
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));let launches=0;
    try {
      for(const level of ['small','medium','large'])for(const game of allowedGames(level)) {
        await page.goto(`${base}/#playroom`);
        await page.evaluate(p=>{localStorage.setItem('taiwan-train-math.v1',JSON.stringify(p));sessionStorage.clear();},{...defaults(),level});
        await page.reload();
        const group=await page.locator(`[data-mission="${game}"]`).evaluate(el=>el.closest('[role="tabpanel"]').id.replace('playroom-panel-',''));
        await press(page,page.locator(`[data-game-category="${group}"]`));await press(page,page.locator(`[data-mission="${game}"]`));
        await page.locator('#trip-exit').waitFor();await guard(page);await tap(page,'#hint-show');await guard(page);
        await page.evaluate(()=>scrollTo(0,document.body.scrollHeight));
        const exit=await page.locator('#trip-exit').boundingBox();assert.ok(exit.y>=0&&exit.y+exit.height<=height,`${level}/${game} pause remains on screen`);
        await press(page,page.locator('#trip-exit'));launches++;
      }
      assert.equal(launches,57);assert.deepEqual(errors,[]);audits.push({name,launches,controlMinimum:44,overflow:false,errors});
    } finally {await context.close();}
  });
}
