import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { CHAPTERS, fieldMission, currentFieldMission, normalizeFieldbook, advanceFieldbook, fieldbookMarkup, fieldbookResultMarkup } from '../src/fieldbook.js';
import { defaults, allowedGames, createTrip, seededRandom, readProgress, saveProgress } from '../src/engine.js';
import { encodeBackup, decodeBackup } from '../src/progress-backup.js';
const { trains } = JSON.parse(readFileSync(new URL('../data/trains.json',import.meta.url),'utf8'));
const tripFor = (level,index,seed=42) => {
  const mission=fieldMission(level,index);
  return { meta:{level,practice:mission.game,journey:null},questions:createTrip({level,practice:mission.game,train:trains[0],trains,rng:seededRandom(seed)}),index:level==='small'?2:4,solved:true,awarded:false };
};
test('all 36 age goals generate reachable, distinct practice trips across seeds', () => {
  for(const level of ['small','medium','large']) {
    const games=[];
    for(let i=0;i<12;i++) {
      const m=fieldMission(level,i); assert.ok(allowedGames(level).includes(m.game)); games.push(m.game);
      assert.ok(m.story.length>5); assert.ok(m.title.length>2);
      for(let seed=1;seed<=12;seed++) {
        const trip=tripFor(level,i,seed);
        assert.equal(trip.questions.length,level==='small'?3:5);
        assert.ok(trip.questions.every(q=>q.game===m.game&&q.level===level));
        assert.ok(trip.questions.every(q=>q.answer!==undefined));
      }
    }
    assert.equal(new Set(games).size,12);
  }
});
test('complete all four chapters separately per age, award only each third goal', () => {
  const p=defaults();
  for(const level of ['small','medium','large']) {
    p.level=level;
    for(let i=0;i<12;i++) {
      assert.equal(currentFieldMission(p).index,i);
      const trip=tripFor(level,i),result=advanceFieldbook(p,trip);
      assert.equal(result.completed,i+1); assert.equal(result.stamp, (i+1)%3===0?CHAPTERS[Math.floor(i/3)]:null);
      assert.equal(advanceFieldbook(p,trip),null,'the same trip cannot advance another goal');
      trip.awarded=true; assert.equal(advanceFieldbook(p,trip),null);
    }
    assert.equal(currentFieldMission(p),null);
    assert.equal((fieldbookMarkup(p,{collection:true}).match(/field-stamp earned/g)||[]).length,4);
  }
  assert.deepEqual(p.fieldbook,{small:12,medium:12,large:12});
});
test('unfinished, mismatched, mixed, historical awarded or malformed trips do not unlock a goal', () => {
  for(const change of [t=>t.solved=false,t=>t.awarded=true,t=>t.index=0,t=>t.meta.practice='mixed',t=>t.meta.journey='forest',t=>t.questions.pop(),t=>t.questions[0].game='order',t=>t.questions[0].level='large']) {
    const p=defaults(),trip=tripFor('small',0); change(trip);
    assert.equal(advanceFieldbook(p,trip),null); assert.deepEqual(p.fieldbook,{small:0,medium:0,large:0});
  }
});
test('progress survives storage and backup, old saves migrate and corrupt fields stay bounded', () => {
  let raw=null;const store={getItem:()=>raw,setItem:(_,s)=>raw=s};
  const p=defaults();p.fieldbook={small:7,medium:2,large:12};p.trips=21;
  assert.ok(saveProgress(store,p));assert.deepEqual(readProgress(store).fieldbook,p.fieldbook);
  assert.deepEqual(decodeBackup(encodeBackup(p)).progress.fieldbook,p.fieldbook);
  raw=JSON.stringify({version:1,trips:3});assert.deepEqual(readProgress(store).fieldbook,{small:0,medium:0,large:0});
  assert.deepEqual(normalizeFieldbook({small:-1,medium:99,large:'3',injected:12}),{small:0,medium:12,large:0});
  for(const bad of [null,[],false,'x',{small:NaN,medium:1.5,large:Infinity}]) assert.deepEqual(normalizeFieldbook(bad),{small:0,medium:0,large:0});
  assert.equal(fieldMission('__proto__',0),null); assert.equal(fieldMission('small',12),null);
});
test('menu and completion offer one real launch, stop after all goals and keep safe labels', () => {
  const p=defaults();assert.equal((fieldbookMarkup(p).match(/data-fieldbook=/g)||[]).length,1);
  const result=advanceFieldbook(p,tripFor('small',0));assert.match(fieldbookResultMarkup(result),/下一個：排好車廂/);
  assert.match(fieldbookMarkup(p),/1／12/);assert.match(fieldbookMarkup(p),/可用提示，隨時休息/);
  p.fieldbook.small=12;assert.doesNotMatch(fieldbookMarkup(p),/data-fieldbook=/);
  const last={level:'small',completed:12,title:'<script>',stamp:null};assert.doesNotMatch(fieldbookResultMarkup(last),/<script>/);
  assert.match(fieldbookResultMarkup(last),/看看四枚收藏章/);
});
