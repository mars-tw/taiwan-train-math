import test from "node:test";
import assert from "node:assert/strict";
import { attachPuzzleTouch, shouldStartPuzzleDrag, puzzleTouchIndex, puzzleDropSlot } from "../src/puzzle-touch.js";

class Classes {
  constructor(values = []) { this.values = new Set(values); }
  add(...values) { values.forEach(value => this.values.add(value)); }
  remove(...values) { values.forEach(value => this.values.delete(value)); }
  contains(value) { return this.values.has(value); }
}
class Style {
  constructor() { this.values = new Map(); }
  setProperty(key, value) { this.values.set(key, value); }
  getPropertyValue(key) { return this.values.get(key) || ""; }
}
class Node {
  constructor(doc, classes = [], attributes = {}) {
    this.ownerDocument = doc;
    this.classList = new Classes(classes);
    this.attributes = new Map(Object.entries(attributes));
    this.style = new Style();
    this.listeners = new Map();
    this.children = [];
    this.disabled = false;
    this.clicks = 0;
    this.rect = { left: 0, top: 0, width: 80, height: 50 };
  }
  addEventListener(type, handler) {
    this.listeners.set(type, [...(this.listeners.get(type) || []), handler]);
  }
  removeEventListener(type, handler) {
    this.listeners.set(type, (this.listeners.get(type) || []).filter(value => value !== handler));
  }
  fire(type, event) {
    for (const handler of [...(this.listeners.get(type) || [])]) {
      handler(event);
      if (event.stopped) break;
    }
    return event;
  }
  append(child) { child.parent = this; this.children.push(child); }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this);
    this.parent = null;
  }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  getAttribute(key) { return this.attributes.get(key) ?? null; }
  setAttribute(key, value) { this.attributes.set(key, String(value)); }
  removeAttribute(key) { this.attributes.delete(key); }
  matches(selector) {
    return selector.split(",").some(part => {
      const value = part.trim();
      if (value.startsWith(".")) return this.classList.contains(value.slice(1));
      if (value.startsWith("#")) return this.attributes.get("id") === value.slice(1);
      return /^\[[^\]]+\]$/.test(value) && this.attributes.has(value.slice(1, -1));
    });
  }
  closest(selector) { return this.matches(selector) ? this : this.parent?.closest(selector) || null; }
  querySelectorAll(selector) {
    return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  getBoundingClientRect() { return this.rect; }
  cloneNode() {
    const clone = new Node(this.ownerDocument, [...this.classList.values], Object.fromEntries(this.attributes));
    for (const child of this.children) clone.append(child.cloneNode(true));
    return clone;
  }
  setPointerCapture(id) { this.capture = id; }
  hasPointerCapture(id) { return this.capture === id; }
  releasePointerCapture() { this.capture = null; }
  click() { this.clicks++; }
}
function harness(options = {}) {
  const doc = new Node();
  doc.ownerDocument = doc;
  const win = new Node(doc);
  doc.defaultView = win;
  doc.body = new Node(doc);
  const root = new Node(doc), stage = new Node(doc, ["puzzle-stage"]);
  doc.body.append(root); root.append(stage);
  const board = new Node(doc, ["puzzle-board"]); stage.append(board);
  const source = new Node(doc, ["puzzle-tray-piece"], { "data-puzzle-piece": "5" });
  source.rect = { left: 20, top: 200, width: 80, height: 50 };
  source.append(new Node(doc, [], { id: "original-child" }));
  stage.append(source);
  const slots = [0, 1, 2].map(index => {
    const slot = new Node(doc, ["puzzle-slot"], { "data-puzzle-slot": String(index) });
    slot.rect.left = index * 80;
    board.append(slot);
    return slot;
  });
  const values = new Style();
  values.setProperty("--puzzle-columns", "3");
  values.setProperty("--puzzle-rows", "3");
  values.setProperty("--puzzle-cell-ratio", "16/9");
  win.getComputedStyle = () => values;
  const observers = [];
  win.MutationObserver = class {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe() {} disconnect() { this.disconnected = true; }
  };
  doc.elementFromPoint = (x, y) => options.hit ||
    (x >= 20 && x < 100 && y >= 200 && y <= 250 ? source :
      y >= 0 && y <= 50 ? slots.find(slot => x >= slot.rect.left && x < slot.rect.left + 80) : null);
  const drops = [], announcements = [];
  const destroy = attachPuzzleTouch(root, { onDrop: (piece, slot) => drops.push([piece, slot]), onAnnounce: message => announcements.push(message) });
  function event(target, extra = {}) {
    return {
      target, pointerId: 1, pointerType: "touch", isPrimary: true, button: 0,
      clientX: 30, clientY: 210, cancelable: true, detail: 1,
      preventDefault() { this.defaultPrevented = true; },
      stopImmediatePropagation() { this.stopped = true; },
      ...extra,
    };
  }
  function down(extra = {}, target = source) {
    const e = event(target, extra);
    doc.fire("pointerdown", e);
    if (root.contains(target)) root.fire("pointerdown", e);
    return e;
  }
  const move = (extra = {}) => doc.fire("pointermove", event(source, { clientX: 120, clientY: 25, ...extra }));
  const up = (extra = {}) => doc.fire("pointerup", event(source, { clientX: 120, clientY: 25, ...extra }));
  const click = (extra = {}, target = source) => doc.fire("click", event(target, extra));
  return { doc, win, root, stage, board, source, slots, drops, announcements, observers, destroy, down, move, up, click, event };
}

test("gesture threshold separates small finger motion from an intentional drag", () => {
  assert.equal(shouldStartPuzzleDrag({ x: 0, y: 0 }, { x: 8, y: 0 }), false);
  assert.equal(shouldStartPuzzleDrag({ x: 0, y: 0 }, { x: 9, y: 0 }), true);
  assert.equal(shouldStartPuzzleDrag({ x: 20, y: 20 }, { x: 26, y: 26 }), false);
  assert.equal(shouldStartPuzzleDrag({ x: 20, y: 20 }, { x: 27, y: 27 }), true);
  for (const point of [null, {}, { x: NaN, y: 2 }, { x: Infinity, y: 2 }])
    assert.equal(shouldStartPuzzleDrag({ x: 0, y: 0 }, point), false);
  for (const value of [null, undefined, "", "-1", "2.5", "Infinity", "1e1", " 2", 2]) assert.equal(puzzleTouchIndex(value), null);
  assert.equal(puzzleTouchIndex("0"), 0);
  assert.equal(puzzleTouchIndex("8"), 8);
});

test("mouse taps and small movements keep the existing native click flow untouched", () => {
  const h = harness();
  const down = h.down({ pointerType: "mouse" });
  h.move({ clientX: 38, clientY: 210 });
  const up = h.up({ clientX: 38, clientY: 210 });
  const click = h.click();
  assert.equal(down.defaultPrevented, undefined);
  assert.equal(up.defaultPrevented, undefined);
  assert.equal(click.stopped, undefined);
  assert.equal(h.source.clicks, 0);
  assert.deepEqual(h.drops, []);
  assert.equal(h.doc.body.children.length, 1);
  h.destroy();
});
test("touch taps invoke the existing button route once when a browser omits its native click", () => {
  const h = harness();
  h.down(); h.move(); h.up();
  h.down(); h.up({ clientX: 30, clientY: 210 });
  assert.equal(h.source.clicks, 1, "a fresh touch tap responds without waiting for a compatibility click");
  assert.equal(h.click().stopped, true, "a later native click from the same touch cannot act a second time");
  assert.equal(h.click({ detail: 0 }).stopped, undefined, "keyboard activation remains available");
  h.down(); h.up({ clientX: 30, clientY: 210 });
  assert.equal(h.source.clicks, 2, "the next physical tap creates exactly one more action");
  assert.deepEqual(h.drops, [[5, 1]], "tap handling never creates a drop or chooses an answer");
  h.destroy();
});
test("empty board touch taps still route to placement; sliding an empty slot never drags", () => {
  const h = harness();
  h.down({ clientX: 100, clientY: 20 }, h.slots[1]);
  h.up({ clientX: 100, clientY: 20 });
  assert.equal(h.slots[1].clicks, 1);
  assert.deepEqual(h.drops, []);
  h.down({ clientX: 100, clientY: 20 }, h.slots[1]);
  h.move({ clientX: 160, clientY: 20 }); h.up({ clientX: 160, clientY: 20 });
  assert.equal(h.slots[1].clicks, 1);
  assert.equal(h.doc.body.children.length, 1);
  h.destroy();
});

test("WebKit's translated mouse click cannot toggle or place twice after pointerId zero touch", () => {
  const h = harness();
  h.down({ pointerId: 0 });
  h.up({ pointerId: 0, clientX: 30, clientY: 210 });
  assert.equal(h.source.clicks, 1);
  assert.equal(h.click({ pointerId: 1, pointerType: "mouse" }).stopped, true);
  h.down({ pointerId: 0 });
  h.up({ pointerId: 0, clientX: 30, clientY: 210 });
  assert.equal(h.source.clicks, 2, "the next finger tap responds once");
  assert.equal(h.click({ pointerId: 1, pointerType: "mouse" }).stopped, true);
  h.down({ pointerId: 1, pointerType: "mouse" });
  h.up({ pointerId: 1, pointerType: "mouse", clientX: 30, clientY: 210 });
  assert.equal(h.click({ pointerId: 1, pointerType: "mouse" }).stopped, undefined, "a fresh real mouse press works");
  h.down({ pointerId: 0 });
  h.move({ pointerId: 0 }); h.up({ pointerId: 0 });
  assert.deepEqual(h.drops, [[5, 1]]);
  assert.equal(h.click({ pointerId: 1, pointerType: "mouse" }).stopped, true, "drag's translated click is also discarded");
  h.destroy();
});
test("only known controls in the current unsolved puzzle receive exactly one touch click", () => {
  for (const id of ["puzzle-preview", "puzzle-reset", "puzzle-submit", "trip-exit", "hint-show", "question-replay", "game-fullscreen"]) {
    const h = harness(), button = new Node(h.doc, [], { id });
    h.root.append(button);
    h.doc.elementFromPoint = () => button;
    h.down(); h.move(); h.up();
    h.down({ clientX: 260, clientY: 210 }, button);
    h.up({ clientX: 260, clientY: 210 });
    assert.equal(button.clicks, 1, `${id} works even outside the puzzle-stage after dragging`);
    assert.equal(h.click({}, button).stopped, true, `${id}'s later native click is suppressed`);
    h.down({ clientX: 260, clientY: 210 }, button);
    h.move({ clientX: 290, clientY: 210 }); h.up({ clientX: 290, clientY: 210 });
    assert.equal(button.clicks, 1, "sliding a dock control creates neither a tap nor a drag");
    h.stage.classList.add("puzzle-solved");
    h.down({ clientX: 260, clientY: 210 }, button); h.up({ clientX: 260, clientY: 210 });
    assert.equal(button.clicks, 1, "the touch primitive does not activate a solved scene's controls");
    h.stage.remove();
    h.down({ clientX: 260, clientY: 210 }, button); h.up({ clientX: 260, clientY: 210 });
    assert.equal(button.clicks, 1, "these common controls keep the native route in other game scenes");
    h.destroy();
  }
  const h = harness(), unrelated = new Node(h.doc, [], { id: "cargo-reset" });
  h.root.append(unrelated);
  h.doc.elementFromPoint = () => unrelated;
  h.down({}, unrelated); h.up();
  assert.equal(unrelated.clicks, 0, "other application controls keep their normal native route");
  h.destroy();
});

test("tray dragging changes no model until release and uses the finger's actual destination", () => {
  const h = harness();
  h.down();
  const moved = h.move();
  assert.equal(moved.defaultPrevented, true);
  assert.deepEqual(h.drops, []);
  assert.equal(h.source.classList.contains("puzzle-drag-source"), true);
  assert.equal(h.slots[1].classList.contains("puzzle-drop-target"), true);
  const ghost = h.doc.body.children[1];
  assert.equal(ghost.classList.contains("puzzle-drag-ghost"), true);
  assert.equal(ghost.getAttribute("data-puzzle-piece"), null);
  assert.equal(ghost.querySelectorAll("[id]").length, 0);
  assert.equal(ghost.style.getPropertyValue("--puzzle-columns"), "3");
  assert.equal(ghost.style.getPropertyValue("--puzzle-cell-ratio"), "16/9");
  assert.equal(ghost.getAttribute("aria-hidden"), "true");
  assert.equal(h.source.children[0].getAttribute("id"), "original-child");
  h.up({ clientX: 200, clientY: 25 });
  assert.deepEqual(h.drops, [[5, 2]], "piece five goes to hit-tested slot two, never to its correct position");
  assert.equal(h.doc.body.children.length, 1);
  assert.equal(h.source.capture, null);
  assert.equal(h.slots[1].classList.contains("puzzle-drop-target"), false);
  h.up();
  assert.deepEqual(h.drops, [[5, 2]], "pointerup is committed exactly once");
  const click = h.click();
  assert.equal(click.stopped, true);
  assert.equal(click.defaultPrevented, true);
  assert.equal(h.click().stopped, undefined, "only the drag's trailing click is swallowed");
  h.destroy();
});

test("placed pieces use their explicit identity and can drop onto an occupied slot", () => {
  const h = harness();
  const placed = h.slots[0];
  placed.setAttribute("data-puzzle-piece-id", "7");
  placed.classList.add("is-filled");
  h.slots[1].setAttribute("data-puzzle-piece-id", "3");
  h.slots[1].classList.add("is-filled");
  h.down({ clientX: 20, clientY: 20 }, placed);
  h.move(); h.up();
  assert.deepEqual(h.drops, [[7, 1]], "source slot zero does not imply piece zero");
  h.destroy();
});

test("returning a placed piece to its own slot does not create a model transaction", () => {
  const h = harness();
  h.slots[0].setAttribute("data-puzzle-piece-id", "7");
  h.down({ clientX: 20, clientY: 20 }, h.slots[0]);
  h.move(); h.up({ clientX: 20, clientY: 20 });
  assert.deepEqual(h.drops, []);
  assert.equal(h.click({}, h.slots[0]).stopped, true);
  h.destroy();
});

test("outside-board drops, pointer cancellation and scrolling leave the model unchanged", () => {
  for (const cancel of [
    h => h.up({ clientX: 300, clientY: 400 }),
    h => h.doc.fire("pointercancel", h.event(h.source)),
    h => h.doc.fire("scroll", h.event(h.root)),
    h => h.doc.fire("contextmenu", h.event(h.source)),
    h => h.win.fire("resize", h.event(h.root)),
    h => h.win.fire("blur", h.event(h.root)),
  ]) {
    const h = harness();
    h.down(); h.move(); cancel(h); h.up();
    assert.deepEqual(h.drops, []);
    assert.equal(h.doc.body.children.length, 1);
    assert.equal(h.source.classList.contains("puzzle-drag-source"), false);
    h.destroy();
  }
});

test("another finger cancels a gesture even when it touches outside the puzzle", () => {
  for (const alreadyDragging of [false, true]) {
    const h = harness();
    h.down();
    if (alreadyDragging) h.move();
    h.down({ pointerId: 2, isPrimary: false }, h.doc.body);
    h.move(); h.up(); h.up({ pointerId: 2 });
    assert.deepEqual(h.drops, []);
    assert.equal(h.doc.body.children.length, 1);
    assert.equal(h.click().stopped, true, "a cancelled multi-touch gesture cannot become a tap action");
    h.destroy();
  }
});

test("redraw removal cancels the gesture and cleans up its visual clone", () => {
  const h = harness();
  h.down(); h.move(); h.source.remove();
  h.observers[0].callback();
  assert.equal(h.doc.body.children.length, 1);
  h.up();
  assert.deepEqual(h.drops, []);
  h.destroy();
});

test("right clicks, blank slots, solved scenes and unrelated pointers cannot drag", () => {
  for (const configure of [
    h => h.down({ pointerType: "mouse", button: 2 }),
    h => h.down({}, h.slots[0]),
    h => { h.stage.classList.add("puzzle-solved"); h.down(); },
    h => { h.source.disabled = true; h.down(); },
    h => { h.source.setAttribute("data-puzzle-piece", "-1"); h.down(); },
  ]) {
    const h = harness(); configure(h); h.move(); h.up();
    assert.deepEqual(h.drops, []);
    assert.equal(h.doc.body.children.length, 1);
    h.destroy();
  }
  const h = harness(); h.down(); h.move({ pointerId: 99 }); h.up({ pointerId: 99 });
  assert.deepEqual(h.drops, []);
  h.up(); h.destroy();
});

test("fresh taps and keyboard activation survive trailing-click protection", () => {
  const h = harness(); h.down(); h.move(); h.up();
  assert.equal(h.click({ detail: 0 }).stopped, undefined, "keyboard activation is never swallowed");
  h.down(); h.up({ clientX: 30, clientY: 210 });
  assert.equal(h.source.clicks, 1, "a fresh physical touch activates the button once");
  assert.equal(h.click().stopped, true, "its own later native click is discarded");
  assert.deepEqual(h.drops, [[5, 1]]);
  h.destroy();
});

test("destroy removes listeners, capture and ghost without a drop callback", () => {
  const h = harness(); h.down(); h.move(); h.destroy(); h.up();
  assert.deepEqual(h.drops, []);
  assert.equal(h.doc.body.children.length, 1);
  assert.equal(h.source.capture, null);
  assert.equal(h.observers[0].disconnected, true);
  assert.ok([...h.doc.listeners.values(), ...h.win.listeners.values(), ...h.root.listeners.values()].every(handlers => handlers.length === 0));
  h.destroy();
});

test("hit testing rejects controls from another root or a disabled board", () => {
  const h = harness();
  assert.equal(puzzleDropSlot(h.root, 100, 20).slot, 1);
  assert.equal(puzzleDropSlot(h.root, 100, 200), null);
  assert.equal(puzzleDropSlot(h.root, NaN, 20), null);
  h.slots[1].disabled = true;
  assert.equal(puzzleDropSlot(h.root, 100, 20), null);
  h.slots[1].disabled = false;
  h.slots[1].setAttribute("data-puzzle-slot", "not-an-index");
  assert.equal(puzzleDropSlot(h.root, 100, 20), null);
  const outsider = new Node(h.doc, ["puzzle-slot"], { "data-puzzle-slot": "0" });
  h.doc.elementFromPoint = () => outsider;
  assert.equal(puzzleDropSlot(h.root, 100, 20), null);
  h.destroy();
  assert.throws(() => attachPuzzleTouch(null, { onDrop() {} }));
  assert.throws(() => attachPuzzleTouch(h.root));
});
