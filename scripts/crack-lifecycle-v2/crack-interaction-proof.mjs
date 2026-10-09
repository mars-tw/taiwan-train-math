import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
export const APP_ID='tw.mars.crackveilvanguard';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const fail=c=>{throw new Error(c)};
export function checkedAuthority(a,m,metadataSha256){
 if(a?.projectId!=='crackveil-vanguard'||a.appId!==APP_ID||a.version!=='1.0.0'||a.build!==2||a.frozen!==true)fail('ROOT_BUILD2_AUTHORITY_NOT_FROZEN');
 for(const k of ['pckSha256','sourceInputManifestSha256','observerSha256'])if(!/^[0-9a-f]{64}$/.test(a[k]||''))fail('CURRENT_BUILD2_PINS_REQUIRED');
 if(m.appId!==APP_ID||m.nativeVersion!=='1.0.0'||m.nativeBuild!==2||m.pckSha256!==a.pckSha256||m.sourceInputManifestSha256!==a.sourceInputManifestSha256)fail('BUILD2_SOURCE_TUPLE_DIFFERS');
 if(a.pckSha256!=='a6676ef12cf8badb262ebdd475db0e6eafb2c74369666f7c8ca56d4d5c1e17d0'||a.sourceInputManifestSha256!=='975871052ae1a04944b009957b09afc0db74ced44bcbcfbd66b48bb3a01cdb0a'||a.observerSha256!=='2f884d6018879a2cb9cdce22aad4e2b14378d21c512550ba558c9d0c6b6d47e4'||metadataSha256!=='e48263485bf4967617d33f6a6fbfac6236c35a7645a0e04de61758586bd315bd')fail('EXACT_OBSERVED_BUILD2_PINS_REQUIRED');
 if(m.sourceFiles!==47||m.rawGameSourceFiles!==634||m.observerSha256!==a.observerSha256||m.observerNormalEnabled!==false)fail('PASSIVE_OBSERVER_SOURCE_BINDING_REQUIRED');
 return Object.freeze({...a});
}
function sample(x){
 const keys=['sequence','ticks_ms','elapsed','player_x','player_y','joystick_x','joystick_y'];
 if(!x||keys.some(k=>!Number.isFinite(x[k]))||!Number.isInteger(x.sequence)||x.sequence<1||x.sequence>15000||x.ticks_ms<0||x.elapsed<0)fail('PASSIVE_SAMPLE_SCHEMA_INVALID');
 for(const k of ['player_instance','scene_instance','run_seed'])if(!Number.isSafeInteger(x[k])||x[k]<0)fail('PASSIVE_IDENTITY_SCHEMA_INVALID');
 for(const k of ['game_running','tree_paused','manual_paused','player_valid','touching'])if(typeof x[k]!=='boolean')fail('PASSIVE_SAMPLE_BOOLEAN_INVALID');
 if(!Array.isArray(x.joy_rect)||x.joy_rect.length!==4||x.joy_rect.some(v=>!Number.isFinite(v))||!Array.isArray(x.viewport)||x.viewport.length!==2||x.viewport.some(v=>!Number.isFinite(v)||v<=0))fail('PASSIVE_GEOMETRY_INVALID');
 return x;
}
export async function startOwnedSampleFeed({container,mirror,kind,authority,nonce}){
 if(!/^[0-9a-f]{32}$/.test(nonce||''))fail('CURRENT_RUNNER_NONCE_REQUIRED');
 const parent=await fs.realpath(container);const st=await fs.lstat(container);if(!st.isDirectory()||st.isSymbolicLink()||!path.isAbsolute(parent))fail('OWNED_CONTAINER_REQUIRED');
 const initial={appId:APP_ID,version:'1.0.0',build:2,pckSha256:authority.pckSha256,kind,nonce,epoch:0,mirrorPathSha256:sha(Buffer.from(mirror)),receivedAtMs:Date.now(),sourceReady:false,samples:[]};
 const initialTemp=mirror+'.tmp';await fs.writeFile(initialTemp,JSON.stringify(initial),{mode:0o600,flag:'wx'});await fs.rename(initialTemp,mirror);
 let file,offset=0,tail='',closed=false,error=null,epoch=0,last=null,total=0,inode=null,writtenSequence=0,pending=Promise.resolve();const samples=[];
 async function find(){
  let count=0;const stack=[[parent,0]],matches=[];
  while(stack.length){const [dir,depth]=stack.pop();for(const e of await fs.readdir(dir,{withFileTypes:true})){
   if(++count>512)fail('OWNED_CONTAINER_LOOKUP_BOUND');const q=path.join(dir,e.name);if(e.isSymbolicLink())continue;
   if(e.isFile()&&e.name==='mars_native_qa.jsonl')matches.push(q);
   else if(e.isDirectory()&&depth<8&&['Library','Application Support','app_userdata','Crackveil Vanguard','CrackveilVanguard','Documents'].includes(e.name))stack.push([q,depth+1]);
  }}
  if(matches.length>1)fail('AMBIGUOUS_OWNED_PASSIVE_FILE');return matches[0];
 }
 async function refresh(){
  if(closed||error)return;
  try{
   file ||= await find();if(!file)return;
   const st=await fs.lstat(file);if(!st.isFile()||st.isSymbolicLink()||st.size>16*1024*1024)fail('PASSIVE_FILE_BOUND_OR_TYPE');
   const real=await fs.realpath(file);if(!real.startsWith(parent+path.sep))fail('PASSIVE_FILE_OUTSIDE_OWNED_CONTAINER');
   if(inode!==null&&(st.ino!==inode||st.size<offset)){epoch++;offset=0;tail='';last=null;writtenSequence=0;}
   inode=st.ino;const h=await fs.open(file,'r');
   try{const actual=await h.stat();if(actual.ino!==st.ino||!actual.isFile())fail('PASSIVE_FILE_REPLACED');
    while(offset<actual.size){const bytes=Buffer.alloc(Math.min(65536,actual.size-offset));const {bytesRead}=await h.read(bytes,0,bytes.length,offset);if(!bytesRead)fail('PASSIVE_FILE_READ_INCOMPLETE');offset+=bytesRead;tail+=bytes.subarray(0,bytesRead).toString('utf8');
     let at;while((at=tail.indexOf('\n'))>=0){const line=tail.slice(0,at);tail=tail.slice(at+1);if(line.length>2048)fail('PASSIVE_LINE_BOUND');if(!line.trim())continue;const x=sample(JSON.parse(line));
      if(!last&&x.sequence!==1)fail('PASSIVE_LAUNCH_SEQUENCE_NOT_FRESH');if(last&&(x.sequence!==last.sequence+1||x.ticks_ms<=last.ticks_ms))fail('PASSIVE_SEQUENCE_DISCONTINUITY');
      last=x;if(++total>30000)fail('PASSIVE_TOTAL_BOUND');samples.push({...x,epoch,hostReadAtMs:Date.now(),hostWriteAtMs:null});
     }if(tail.length>2048)fail('PASSIVE_PARTIAL_LINE_BOUND');
    }
   }finally{await h.close();}
   if(last&&last.sequence!==writtenSequence){writtenSequence=last.sequence;const envelope={appId:APP_ID,version:'1.0.0',build:2,pckSha256:authority.pckSha256,kind,nonce,epoch,sourceReady:true,mirrorPathSha256:sha(Buffer.from(mirror)),receivedAtMs:Date.now(),samples:samples.filter(s=>s.epoch===epoch).slice(-300)};
    const tmp=mirror+'.tmp';await fs.writeFile(tmp,JSON.stringify(envelope),{mode:0o600});await fs.rename(tmp,mirror);
     const completed=Date.now();for(const row of samples)if(row.hostWriteAtMs===null)row.hostWriteAtMs=completed; // actual completed mirror write, diagnostics only; no additional write or heartbeat.
   }
  }catch(e){error=e instanceof Error&&/^[A-Z0-9_]{1,100}$/.test(e.message)?e.message:'PASSIVE_IO_UNKNOWN';}
 }
 const timer=setInterval(()=>{pending=pending.then(refresh)},100);pending=pending.then(refresh);
 return {async stop(){clearInterval(timer);await pending;closed=true;return {samples,error,total,nonce,fileRead:Boolean(file),sampleFileSha256:file?sha(await fs.readFile(file)):null,physicalDeviceTested:false};}};
}
export function proveInteraction({testText,feed,kind,authority,phase='complete'}){
 if(!['cold','complete'].includes(phase))fail('INVALID_PROOF_PHASE');
 if(feed.error||!feed.fileRead)fail(feed.error||'ACTUAL_PASSIVE_FILE_MISSING');
 const rows=testText.split(/\r?\n/).filter(s=>s.startsWith('CRACK_QA_EVENT ')).map(s=>JSON.parse(s.slice(15)));
 const actions=['start','move','pause','paused-wait','resume'];const proof={};
 for(const action of actions){const begin=rows.filter(r=>r.action===action&&r.phase==='begin'),end=rows.filter(r=>r.action===action&&r.phase==='end');
  if(begin.length!==1||end.length!==1||begin[0].kind!==kind||end[0].kind!==kind||begin[0].epoch!==end[0].epoch||end[0].sequence<=begin[0].sequence)fail('GESTURE_INTERVAL_NOT_BOUND');
  const a=begin[0],b=end[0],s=feed.samples.filter(s=>s.epoch===a.epoch&&s.sequence>=a.sequence&&s.sequence<=b.sequence);
  if(s.length<2||s[0].sequence!==a.sequence||s.at(-1).sequence!==b.sequence||s[0].ticks_ms!==a.ticks_ms||s.at(-1).ticks_ms!==b.ticks_ms)fail('GESTURE_INTERVAL_SAMPLES_MISSING');
  proof[action]={epoch:a.epoch,firstSequence:a.sequence,lastSequence:b.sequence,sampleCount:s.length,firstTicksMs:a.ticks_ms,lastTicksMs:b.ticks_ms};
  if(['move','paused-wait','resume'].includes(action)){
   const identity=['player_instance','scene_instance','run_seed'];
   if(s.some(v=>!v.player_valid||!v.game_running||identity.some(k=>!Number.isSafeInteger(v[k])||v[k]<=0||v[k]!==s[0][k])))fail('ACTION_IDENTITY_RESET_OR_UNKNOWN');
   proof[action].entityIdentity=Object.fromEntries(identity.map(k=>[k,s[0][k]]));
   if(action!=='move'&&identity.some(k=>proof[action].entityIdentity[k]!==proof.move.entityIdentity[k]))fail('PAUSE_RESUME_ENTITY_CHANGED');
  }
  if(action==='move'){
   const identity=['player_instance','scene_instance','run_seed'];
   if(s.some(v=>identity.some(k=>!Number.isSafeInteger(v[k])||v[k]<=0||v[k]!==s[0][k])))fail('MOVE_IDENTITY_RESET_OR_UNKNOWN');
   if(s.some((v,i)=>i>0&&(v.sequence!==s[i-1].sequence+1||v.ticks_ms<=s[i-1].ticks_ms)))fail('MOVE_SEQUENCE_DISCONTINUITY');
   if(s.some((v,i)=>!v.game_running||!v.player_valid||v.tree_paused||v.manual_paused||v.joy_rect[2]<=0||v.joy_rect[3]<=0||(i>0&&v.ticks_ms-s[i-1].ticks_ms>500)||v.viewport.some((n,j)=>n!==s[0].viewport[j])||v.joy_rect.some((n,j)=>Math.abs(n-s[0].joy_rect[j])>1)))fail('SHORT_RUN_CONTINUITY_UNCONFIRMED');
   const held=s.filter(v=>v.touching&&v.joystick_x>=0.35&&Math.abs(v.joystick_y)<0.35&&v.game_running&&v.player_valid&&!v.tree_paused);
   if(held.length<3||held.at(-1).ticks_ms-held[0].ticks_ms<400||held.at(-1).player_x-held[0].player_x<=20||held.at(-1).elapsed-held[0].elapsed<0.3)fail('REAL_TOUCH_MOVEMENT_UNPROVEN');
   proof.move.displacementX=held.at(-1).player_x-held[0].player_x;
  }
  if(action==='paused-wait'&&(s.some(v=>!v.tree_paused||!v.manual_paused)||s.at(-1).ticks_ms-s[0].ticks_ms<500||Math.max(...s.map(v=>v.elapsed))-Math.min(...s.map(v=>v.elapsed))>0.03))fail('ACTUAL_PAUSE_TIMER_NOT_FROZEN');
  if(action==='resume'&&(!s.at(-1).game_running||s.at(-1).tree_paused||s.at(-1).manual_paused||s.at(-1).elapsed-s[0].elapsed<0.5))fail('ACTUAL_RESUME_TIMER_UNPROVEN');
 }
 if(!testText.includes('CRACK_QA_HUD_VERIFIED='+kind)||(phase==='complete'&&!testText.includes('CRACK_QA_WARM_MENU_VERIFIED='+kind))||!testText.includes('CAPTURE_MENU90_FOREGROUND=true'))fail('ACTUAL_SCREEN_STATE_UNPROVEN');
 return {actualNativeForegroundVerified:true,menuVisible:true,hudVisibleAfterStart:true,warmSceneVisible:phase==='complete',startActionCount:1,touchMoveVerified:true,movementContinuity:'SAME_NONZERO_PLAYER_SCENE_SEED_CONTINUOUS_INTERVAL',pauseResumeVerified:true,passiveSource:'own-appdata/user://mars_native_qa.jsonl',sampleFileSha256:feed.sampleFileSha256,proof,physicalDeviceTested:false,pckSha256:authority.pckSha256};
}

export function createRunnerBootstrapGate(expected,onBootstrap){
 const e=Object.freeze({...expected});let entered=false,seen=false,closed=false,settled=false,error=null,work=Promise.resolve();
 const reject=c=>{error ||= c;};
 return {
  line(line){
   if(closed)return;
   if(line==='CAPTURE_TEST_METHOD_ENTERED='+e.kind){if(entered)reject('BOOTSTRAP_ENTRY_DUPLICATE');entered=true;return;}
   if(!line.startsWith('CRACK_QA_RUNNER_BOOTSTRAP '))return;
   if(seen){reject('BOOTSTRAP_DUPLICATE');return;}seen=true;
   try{
    const b=JSON.parse(line.slice(26));
    if(!entered||b.protocol!=='CRACK_RUNNER_V1'||b.kind!==e.kind||b.nonce!==e.nonce||b.runnerBundleId!==e.runnerId||!/^[0-9a-f]{64}$/.test(b.mirrorPathSha256||'')||Object.keys(b).sort().join(',')!=='kind,mirrorPathSha256,nonce,protocol,runnerBundleId')throw new Error('BOOTSTRAP_IDENTITY_OR_ORDER');
    work=Promise.resolve().then(()=>{if(error||closed)throw new Error('BOOTSTRAP_NOT_ACTIVE');return onBootstrap(b,()=>!error&&!closed);}).then(()=>{settled=true;},()=>{settled=true;reject('BOOTSTRAP_CONTAINER_BINDING_FAILED');});
   }catch{reject('BOOTSTRAP_IDENTITY_OR_ORDER');}
  },
  error(){return error;},
  async finish(){if(!entered||!seen)reject('BOOTSTRAP_MISSING');if(seen&&!settled)reject('BOOTSTRAP_CHILD_EXIT_BEFORE_READY');closed=true;await work;return error;}
 };
}
