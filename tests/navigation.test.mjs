import test from "node:test";
import assert from "node:assert/strict";
import { resolvePage } from "../src/navigation.js";
test("normal home loads the story while former launch links share one game room", () => {
  for(const hash of ["", "#home", "#story-scene", "unknown", null, "#constructor", '#"><script>'])
    assert.deepEqual(resolvePage(hash),{view:"home",anchor:null,openJourneys:false});
  for(const hash of ["#playroom", "#missions", "#quick-play"])
    assert.deepEqual(resolvePage(hash),{view:"playroom",anchor:null,openJourneys:false});
});
test("old departure anchors and optional journeys retain predictable targets", () => {
  for(const hash of ["#departure","#railway-map"])
    assert.deepEqual(resolvePage(hash),{view:"home",anchor:"departure",openJourneys:false});
  assert.deepEqual(resolvePage("#theme-journeys"),{view:"playroom",anchor:"theme-journeys",openJourneys:true});
  for(const hash of ["collection","stamps"]) assert.equal(resolvePage(hash).view,hash);
});
