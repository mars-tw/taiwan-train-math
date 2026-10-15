import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';

const phase = process.argv[2] || 'after';
if (!['before', 'after'].includes(phase)) throw new Error('Use before or after');
const base = process.env.TRAIN_MATH_URL || 'http://127.0.0.1:5113';
const out = 'docs/evidence/r2-mobile';
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const report = [];
try {
  for (const [name, width, height] of [['portrait',390,844],['landscape',844,390],['desktopShort',1366,600],['laptop',1280,640]]) {
    const context = await browser.newContext({ viewport: { width,height }, isMobile: width < 1000, hasTouch: width < 1000, reducedMotion: 'reduce' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.screenshot({ path: `${out}/${phase}-${name}-home.png` });
    await page.goto(`${base}/#playroom`);
    await page.locator('#playroom-title').waitFor();
    await page.screenshot({ path: `${out}/${phase}-${name}-playroom.png` });
    await page.locator('[data-mission="count"]').click();
    await page.locator('#trip-exit').waitFor();
    await page.screenshot({ path: `${out}/${phase}-${name}-game.png` });
    const audit = await page.evaluate(() => {
      const controls = [...document.querySelectorAll('#main button:not(:disabled)')].filter(el => el.getClientRects().length);
      return { overflow: document.documentElement.scrollWidth > innerWidth,
        controls: controls.map(el => { const r = el.getBoundingClientRect(); const hit = document.elementFromPoint(r.x+r.width/2,r.y+r.height/2); return { id:el.id, text:el.textContent.trim(), width:r.width,height:r.height,inView:r.top>=0&&r.bottom<=innerHeight,unblocked:!!hit&&(hit===el||el.contains(hit)) }; }) };
    });
    report.push({ name,width,height,errors,...audit });
    if(phase==='after') {
      await page.evaluate(()=>scrollTo(0,document.body.scrollHeight));
      await page.screenshot({path:`${out}/${phase}-${name}-scrolled-game.png`});
    }
    await context.close();
  }
  await writeFile(`${out}/${phase}-audit.json`, JSON.stringify(report,null,2));
} finally { await browser.close(); }
console.log(`${phase}: ${report.length} viewports captured, ${report.reduce((n,r)=>n+r.errors.length,0)} page errors`);
