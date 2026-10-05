import test from "node:test";
import assert from "node:assert/strict";
import { createPhotoLoader } from "../src/photo-loader.js";
function fixture() {
  const pictures = [], changes = [];
  const loader = createPhotoLoader({ makeImage: () => { const picture = { naturalWidth: 960 }; pictures.push(picture); return picture; }, onChange: path => changes.push(path) });
  return { loader, pictures, changes };
}
test("a photo task waits for every distinct picture and shares successful loads", () => {
  const {loader,pictures}=fixture(), a="assets/images/real-700t.jpg", b="assets/images/real-emu900.jpg";
  assert.equal(loader.status([a,a,b]), "loading"); assert.equal(pictures.length, 2);
  pictures[0].onload(); assert.equal(loader.status([a,b]), "loading");
  pictures[1].onload(); assert.equal(loader.status([a,b]), "ready"); assert.equal(pictures.length, 2);
});
test("failure stays explicit until a new retry finishes; stale callbacks cannot undo recovery", () => {
  const {loader,pictures}=fixture(), path="assets/images/real-700t.jpg";
  loader.status([path]); pictures[0].onerror(); assert.equal(loader.status([path]), "error");
  loader.retry([path]); assert.equal(loader.status([path]), "loading"); assert.match(loader.source(path), /\?photo-retry=/);
  pictures[0].onload(); assert.equal(loader.status([path]), "loading");
  pictures[1].onload(); assert.equal(loader.status([path]), "ready");
  loader.report(path, "error"); assert.equal(loader.status([path]), "ready");
  loader.report(loader.source(path), "error"); assert.equal(loader.status([path]), "error");
});
test("missing pixels and unsafe image paths never count as playable photographs", () => {
  const {loader,pictures}=fixture(), path="assets/images/real-700t.jpg";
  for(const bad of ["https://example.com/file.jpg","assets/images/../secret.jpg", "assets/images/file.svg"])
    assert.equal(loader.status([bad]), "error");
  assert.equal(pictures.length, 0); loader.status([path]); pictures[0].naturalWidth=0; pictures[0].onload();
  assert.equal(loader.status([path]), "error"); assert.equal(loader.status([]), "ready");
});

test("a stalled request becomes retryable, while a late old response cannot override the retry", () => {
  const timers = [], pictures = [], canceled = [];
  const loader = createPhotoLoader({ makeImage: () => { const p = {naturalWidth:960}; pictures.push(p); return p; },
    schedule: callback => { timers.push(callback); return timers.length - 1; }, cancel: id => canceled.push(id) });
  const path="assets/images/real-700t.jpg";
  assert.equal(loader.status([path]), "loading"); timers[0](); assert.equal(loader.status([path]), "error");
  loader.retry([path]); assert.equal(loader.status([path]), "loading"); pictures[0].onload();
  assert.equal(loader.status([path]), "loading"); pictures[1].onload(); assert.equal(loader.status([path]), "ready");
  assert.ok(canceled.includes(0) && canceled.includes(1));
});
