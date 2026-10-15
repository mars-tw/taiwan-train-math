import { chromium } from 'playwright';
import { writeFile } from 'node:fs/promises';
const browser=await chromium.launch({headless:true});
const results=[];
try {
  for(const [name,width,height] of [['mobile',390,844],['desktop',1366,600]]) {
    const runs=[];
    for(let i=0;i<3;i++) {
      const page=await browser.newPage({viewport:{width,height},hasTouch:width<1000});
      await page.goto(process.env.TRAIN_MATH_URL||'http://127.0.0.1:5113',{waitUntil:'networkidle'});
      const timing=await page.evaluate(()=>new Promise(resolve=>{
        const values=[];let prior;const sample=now=>{if(prior)values.push(now-prior);prior=now;if(values.length<120)requestAnimationFrame(sample);else {values.sort((a,b)=>a-b);resolve({frames:values.length,p95:values[Math.ceil(values.length*.95)-1]});}};requestAnimationFrame(sample);
      }));
      runs.push(timing);await page.close();
    }
    results.push({name,width,height,runs,medianP95:[...runs.map(r=>r.p95)].sort((a,b)=>a-b)[1]});
  }
}finally{await browser.close();}
await writeFile('docs/evidence/r2-mobile/perf.json',JSON.stringify({status:'EXECUTED',measurementContext:'並發載量測，僅供參考',shippingPerformanceGate:'BLOCKED: requires uncontended physical devices',metric:'headless Chromium home requestAnimationFrame interval; not CPU/GPU render time',results},null,2));
console.log('Concurrent-load samples saved; no shipping performance pass claimed.');
