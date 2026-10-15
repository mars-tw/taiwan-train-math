import test from 'node:test';
import assert from 'node:assert/strict';
import { dispatchLesson, dispatchAction, normalizeDispatch, dispatchMarkup } from '../src/dispatch.js';
import { defaults, readProgress, STORAGE_KEY } from '../src/engine.js';
import { encodeBackup, decodeBackup } from '../src/progress-backup.js';
import { backAction } from '../src/native-runtime.js';
const step = (s, a, level) => dispatchAction(s, a, level).state;
test('all age lessons conserve passengers, require three goals, retry freely and award once', () => {
  for(const level of ['small','medium','large']) {
    let s=normalizeDispatch();
    for(let cycle=0;cycle<12;cycle++) {
      s=step(s,'start',level); const q=dispatchLesson(level,cycle);
      assert.ok(q.capacity>=q.total, 'every passenger has a visible seat');
      s=step(s,'check'); assert.equal(s.active.phase,'intro');
      s=step(s,'learn');s=step(s,'check'); assert.equal(s.active.phase,'load');
      for(let n=0;n<q.total;n++)s=step(s,'add');
      s=step(s,'add');assert.equal(s.active.front,q.total);
      s=step(s,'check');assert.equal(s.active.phase,'split');
      s=step(s,'to-rear');s=step(s,'to-front');assert.equal(s.active.front+s.active.rear,q.total);
      for(let n=0;n<q.rear;n++) {s=step(s,'to-rear');assert.equal(s.active.front+s.active.rear,q.total);}
      s=step(s,'check');assert.equal(s.active.phase,'subtract');
      s=step(s,`answer:${q.front+1}`);assert.equal(s.active.phase,'subtract');
      s=step(s,`answer:${q.front}`);assert.equal(s.active.phase,'done');assert.equal(s.completed,cycle+1);
      s=step(s,`answer:${q.front}`);assert.equal(s.completed,cycle+1);
      assert.deepEqual(normalizeDispatch(JSON.parse(JSON.stringify(s))),s);
    }
  }
});
test('old passports default safely and malformed active quantities are discarded', () => {
  assert.deepEqual(readProgress({getItem:()=>JSON.stringify({version:1})}).dispatch,{completed:0,active:null});
  for(const active of [{level:'small',phase:'split',front:99,rear:1},{level:'small',phase:'subtract',front:5,rear:0},{level:'small',phase:'load',front:NaN,rear:0},{level:'small',phase:'done',front:4,rear:1},{level:'__proto__',phase:'intro',front:0,rear:0}])
    assert.equal(normalizeDispatch({completed:0,active}).active,null);
});
test('partially loaded carriages and completed counts survive passport validation and backup', () => {
  const progress=defaults();progress.dispatch=step(step(step(null,'start'),'learn'),'add');
  const stored=readProgress({getItem:key=>key===STORAGE_KEY?JSON.stringify(progress):null});
  assert.deepEqual(stored.dispatch,progress.dispatch);
  assert.deepEqual(decodeBackup(encodeBackup(progress)).progress.dispatch,progress.dispatch);
  assert.equal(backAction({view:'dispatch'}),'go-home');
  assert.match(dispatchMarkup(progress.dispatch),/第 1 站：請 5 人上車/);
});
