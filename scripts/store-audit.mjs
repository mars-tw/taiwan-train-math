import { execFileSync } from 'node:child_process';
import { readFile, writeFile, mkdir, stat, readdir } from 'node:fs/promises';
import { resolve, relative, extname, join } from 'node:path';
import { createHash } from 'node:crypto';
const root=process.cwd(), parent=resolve(root,'..'), out='docs/evidence/r3-store';
await mkdir(out,{recursive:true});
const peers=['rift-survivors','storm-apocalypse','doomsday-shooter','tower-defense','skill','pixel-idle-farm-skill','village-siege','seven-district-reckoning','rift-forge-3d','taiwan-island-drive','island-flight-school','taiwan-train-school'];
const tracked=dir=>{try{return execFileSync('git',['-c','core.quotepath=false','ls-files','-z'],{cwd:dir,encoding:'utf8',maxBuffer:12*1024*1024}).split('\0').filter(Boolean);}catch{return [];}};
const relevant=f=>/^(assets\/|src\/|native\/|index\.html$|manifest\.webmanifest$|ios\/.*(?:Assets.xcassets|LaunchScreen)|android\/.*(?:res\/|MainActivity))/.test(f)&&/\.(?:png|jpe?g|webp|svg|js|css|html|json|webmanifest|swift|java|xml|storyboard)$/.test(f);
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const own=new Map(), comparisons=[], missing=[];
const localFiles=execFileSync('git',['-c','core.quotepath=false','ls-files','--cached','--others','--exclude-standard','-z'],{cwd:root,encoding:'utf8'}).split('\0').filter(Boolean);
for(const path of localFiles.filter(relevant)){try{const bytes=await readFile(join(root,path));if(bytes.length) {const h=hash(bytes);if(!own.has(h))own.set(h,[]);own.get(h).push(path);}}catch{}}
for(const peer of peers){const paths=tracked(join(parent,peer)).filter(relevant);if(!paths.length)missing.push(peer);for(const path of paths){try{const bytes=await readFile(join(parent,peer,path));const h=hash(bytes);if(own.has(h))for(const file of own.get(h))comparisons.push({file,peer,peerFile:path,sha256:h,bytes:bytes.length});}catch{}}}
const codeTokens=[];
for(const peer of peers){for(const path of tracked(join(parent,peer)).filter(f=>/^(?:src\/.*\.css|index\.html|package\.json)$/.test(f)).slice(0,40)){try{const t=await readFile(join(parent,peer,path),'utf8');const markers=['--ink: #203d40','--paper: #faf8f1','Noto Sans TC','Noto Serif TC','@capacitor/core','lobby-departure','story-scene','拆合車廂調度台'].filter(m=>t.includes(m));if(markers.length)codeTokens.push({peer,path,markers});}catch{}}}
const nativeKit=join(parent,'game-store-publisher','native-kit');
const nightRoot=join(nativeKit,'apps','night-train-watch-protocol','web');
let nightFiles=0;
async function compareNight(dir,prefix='') {
  for(const entry of await readdir(dir,{withFileTypes:true}).catch(()=>[])) {
    if(entry.isSymbolicLink()||entry.name.startsWith('.'))continue;
    const path=prefix+entry.name;
    if(entry.isDirectory())await compareNight(join(dir,entry.name),path+'/');
    else if(/\.(?:png|jpe?g|webp|svg|js|css|html|json|webmanifest)$/.test(path)) {
      const bytes=await readFile(join(dir,entry.name));nightFiles++;const h=hash(bytes);
      if(own.has(h))for(const file of own.get(h))comparisons.push({file,peer:'night-train-watch-protocol (native-kit snapshot)',peerFile:path,sha256:h,bytes:bytes.length});
    }
  }
}
await compareNight(nightRoot);
const expected=join(nativeKit,'apps','taiwan-train-math');
const nativeKitMathExists=await stat(expected).then(x=>x.isDirectory()).catch(()=>false);
const report={status:'EXECUTED',date:'2026-10-15',method:'Read-only git runtime source/art hashes plus night-train native-kit historical payload; excludes dependencies/build outputs. Exact equality is not proof of shared authorship.',peers,missing,ownHashedFiles:[...own.values()].flat().length,duplicates:comparisons,sharedMarkers:codeTokens,nativeKitMathExists,nightTrainSnapshot:{path:relative(parent,nightRoot),files:nightFiles,currentSourceVerified:false}};
await writeFile(`${out}/shared-assets.json`,JSON.stringify(report,null,2));
console.log(`Audited ${report.ownHashedFiles} files against ${peers.length} peer repos; ${comparisons.length} exact pairs. native-kit math directory: ${nativeKitMathExists}`);
