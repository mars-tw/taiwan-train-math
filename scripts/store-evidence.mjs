import { readFile, writeFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import sharp from 'sharp';
const root='docs/evidence/r3-store', store='docs/store/screenshots';
const sha=b=>createHash('sha256').update(b).digest('hex');
const decode=bytes=>(bytes[0]===255&&bytes[1]===254?bytes.subarray(2).toString('utf16le'):bytes.toString('utf8')).replace(/^\uFEFF/,'');
for(const [file,total] of [['unit-tests.txt',232],['mobile-e2e-60px.txt',9],['reviewer-tests.txt',20]]) {
  const log=decode(await readFile(`${root}/${file}`));
  if(!log.includes(`pass ${total}`)||!log.includes('fail 0'))throw new Error(`Final tests are not green: ${file}`);
}
if(!decode(await readFile(`${root}/python-tests.txt`)).includes('OK'))throw new Error('Python regression is not green');
async function files(dir){const out=[];for(const entry of await readdir(dir,{withFileTypes:true})){if(entry.isDirectory())out.push(...await files(join(dir,entry.name)));else out.push(join(dir,entry.name).replaceAll('\\','/'));}return out.sort();}
// Receipts stay byte-identical after a Windows/Linux checkout.
for(const path of await files(root))if(/\.(?:txt|json)$/.test(path)){const bytes=await readFile(path);await writeFile(path,decode(bytes).replaceAll('\r\n','\n').replace(/[ \t]+(?=\n|$)/g,''));}
const shots=[];
for(const path of (await files(store)).filter(p=>p.endsWith('.png'))){const bytes=await readFile(path),m=await sharp(bytes).metadata();const phone=path.includes('storePhone');if(m.width!==(phone?1290:2064)||m.height!==(phone?2796:2752))throw new Error(`Wrong screenshot size: ${path}`);shots.push({path:path.split('/').at(-1),width:m.width,height:m.height,bytes:bytes.length,sha256:sha(bytes),cssViewport:phone?[430,932]:[1032,1376],deviceScaleFactor:phone?3:2});}
if(shots.length!==8)throw new Error('Expected eight real gameplay screenshots');
await writeFile(`${store}/manifest.json`,JSON.stringify({status:'VERIFIED',version:'1.14.0',capture:'Headless Chromium actual UI, reduced motion, no compositing; not native-device evidence',script:'tests/store-review.e2e.mjs',files:shots},null,2)+'\n');
const entries=[];
for(const path of (await files(root)).filter(p=>!p.endsWith('/evidence-manifest.json'))){const bytes=await readFile(path);entries.push({path:path.slice(root.length+1),bytes:bytes.length,sha256:sha(bytes)});}
await writeFile(`${root}/evidence-manifest.json`,JSON.stringify({status:'VERIFIED',version:'1.14.0',files:entries},null,2)+'\n');
console.log(`Verified ${shots.length} screenshots; hashed ${entries.length} evidence files.`);
