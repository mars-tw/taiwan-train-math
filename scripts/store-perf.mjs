import { chromium } from 'playwright';
import { writeFile } from 'node:fs/promises';
import { createPreviewServer } from './serve.mjs';
const server=await createPreviewServer({root:process.cwd()});await new Promise(r=>server.listen(0,'127.0.0.1',r));
const browser=await chromium.launch({headless:true}),results=[];
try {
 for(const [name,width,height] of [['mobile',390,844],['desktop',1366,600]])for(const scene of ['home','dispatch']) {
  const runs=[];
  for(let run=0;run<3;run++) {
   const page=await browser.newPage({viewport:{width,height}});await page.goto(`http://127.0.0.1:${server.address().port}/${scene==='dispatch'?'#dispatch':''}`,{waitUntil:'networkidle'});
   const timing=await page.evaluate(()=>new Promise(resolve=>{const samples=[];let previous;function frame(now){if(previous)samples.push(now-previous);previous=now;if(samples.length===120){samples.sort((a,b)=>a-b);resolve({frames:samples.length,p95:samples[Math.ceil(samples.length*.95)-1]});}else requestAnimationFrame(frame);}requestAnimationFrame(frame);}));
   runs.push(timing);await page.close();
  }
  results.push({name,scene,runs,p95Median:runs.map(r=>r.p95).sort((a,b)=>a-b)[1]});
 }
 await writeFile('docs/evidence/r3-store/perf.json',JSON.stringify({status:'EXECUTED',measurementContext:'並發載量測，僅供參考',shippingPerformanceGate:'BLOCKED: requires uncontended physical devices',metric:'Headless rAF intervals, not CPU/GPU render time',results},null,2));
 console.log('Concurrent-load samples recorded; no shipping performance pass claimed.');
}finally{await browser.close();await new Promise(r=>server.close(r));}
