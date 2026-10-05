export const PUZZLE_DRAG_THRESHOLD = 9;
const PUZZLE_TAP_CONTROLS = [
  "puzzle-preview", "puzzle-reset", "puzzle-submit",
  "trip-exit", "hint-show", "question-replay", "game-fullscreen",
];
const PUZZLE_SOURCE_SELECTOR = [
  "[data-puzzle-piece]", "[data-puzzle-piece-id]", "[data-puzzle-slot]",
  ...PUZZLE_TAP_CONTROLS.map(id => `#${id}`),
].join(", ");

export function puzzleTouchIndex(value) {
  if (typeof value !== "string" || !/^\d+$/.test(value)) return null;
  const index = Number(value);
  return Number.isSafeInteger(index) && index >= 0 ? index : null;
}

export function shouldStartPuzzleDrag(start, current, threshold = PUZZLE_DRAG_THRESHOLD) {
  if (![start?.x, start?.y, current?.x, current?.y, threshold].every(Number.isFinite) || threshold < 0)
    return false;
  return Math.hypot(current.x - start.x, current.y - start.y) >= threshold;
}

export function puzzleDropSlot(root, x, y) {
  if (!root || ![x, y].every(Number.isFinite)) return null;
  const hit = root.ownerDocument.elementFromPoint(x, y);
  const slot = hit?.closest?.("[data-puzzle-slot]");
  if (!slot || !root.contains(slot) || slot.disabled || !slot.closest(".puzzle-board")) return null;
  const index = puzzleTouchIndex(slot.getAttribute("data-puzzle-slot"));
  return index === null ? null : { element: slot, slot: index };
}

// Pointer gestures only provide the piece and the finger's actual destination.
// The caller remains responsible for the model transaction and answer checking.
export function attachPuzzleTouch(root, { onDrop, onAnnounce = () => {} } = {}) {
  if (!root?.ownerDocument || typeof onDrop !== "function")
    throw new Error("Puzzle touch needs a root and an onDrop callback");
  const doc = root.ownerDocument, win = doc.defaultView;
  const pointers = new Set(), listeners = [];
  let gesture = null, suppressedClick = null, destroyed = false;

  function listen(target, type, handler, options) {
    target.addEventListener(type, handler, options);
    listeners.push(() => target.removeEventListener(type, handler, options));
  }
  function suppress(pointerId) {
    suppressedClick = { pointerId, until: Date.now() + 700 };
  }
  function cleanGesture() {
    if (!gesture) return;
    const old = gesture;
    gesture = null;
    old.ghost?.remove();
    old.target?.classList.remove("puzzle-drop-target");
    old.source.classList.remove("puzzle-drag-source");
    try {
      if (old.source.hasPointerCapture?.(old.pointerId)) old.source.releasePointerCapture(old.pointerId);
    } catch { /* The source may have been replaced by a redraw. */ }
  }
  function cancel(blockTap = false) {
    if (!gesture) return;
    if (gesture.dragging || blockTap) suppress(gesture.pointerId);
    const wasDragging = gesture.dragging;
    cleanGesture();
    if (wasDragging) onAnnounce("這片還在原位，可以再拖一次。");
  }
  function pieceSource(target) {
    const source = target?.closest?.(PUZZLE_SOURCE_SELECTOR);
    const control = PUZZLE_TAP_CONTROLS.includes(source?.getAttribute("id"));
    const stage = source?.closest(".puzzle-stage") || (control ? root.querySelector(".puzzle-stage") : null);
    if (!source || !root.contains(source) || source.disabled || !stage || stage.classList.contains("puzzle-solved")) return null;
    if (control) return { source, stage, id: null };
    const value = source.getAttribute("data-puzzle-piece") ?? source.getAttribute("data-puzzle-piece-id");
    const id = puzzleTouchIndex(value);
    if (value !== null) return id === null ? null : { source, stage, id };
    return source.closest(".puzzle-board") && puzzleTouchIndex(source.getAttribute("data-puzzle-slot")) !== null
      ? { source, stage, id: null } : null;
  }
  function guardDown(event) {
    // A fresh physical press must never be swallowed as the preceding drag's click.
    suppressedClick = null;
    pointers.add(event.pointerId);
    if (pointers.size > 1) cancel(true);
  }
  function down(event) {
    if (destroyed || gesture || pointers.size > 1 || event.isPrimary === false ||
      (event.pointerType === "mouse" && event.button !== 0) ||
      ![event.clientX, event.clientY].every(Number.isFinite)) return;
    const piece = pieceSource(event.target);
    if (!piece) return;
    gesture = {
      ...piece, pointerId: event.pointerId,
      pointerType: event.pointerType,
      start: { x: event.clientX, y: event.clientY },
      rect: piece.source.getBoundingClientRect(),
      sourceSlot: puzzleTouchIndex(piece.source.getAttribute("data-puzzle-slot")),
      dragging: false, ghost: null, target: null,
    };
    // No model callback, default prevention or visual movement occurs on a tap.
  }
  function startGhost() {
    const g = gesture, ghost = g.source.cloneNode(true);
    ghost.classList.add("puzzle-drag-ghost");
    ghost.classList.remove("is-selected");
    for (const attribute of ["id", "data-puzzle-piece", "data-puzzle-piece-id", "data-puzzle-slot"])
      ghost.removeAttribute(attribute);
    for (const child of ghost.querySelectorAll("[id]")) child.removeAttribute("id");
    ghost.setAttribute("aria-hidden", "true");
    ghost.setAttribute("tabindex", "-1");
    ghost.disabled = true;
    ghost.style.pointerEvents = "none";
    const computed = win.getComputedStyle(g.source);
    for (const property of ["--puzzle-columns", "--puzzle-rows", "--puzzle-cell-ratio"])
      ghost.style.setProperty(property, computed.getPropertyValue(property));
    ghost.style.width = `${g.rect.width}px`;
    ghost.style.height = `${g.rect.height}px`;
    doc.body.append(ghost);
    g.ghost = ghost;
    g.dragging = true;
    g.source.classList.add("puzzle-drag-source");
    try { g.source.setPointerCapture?.(g.pointerId); } catch { /* Document listeners also retain the gesture. */ }
    onAnnounce("拖到想放的格子，再放開。");
  }
  function move(event) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    if (!root.contains(gesture.source) || pointers.size > 1) { cancel(true); return; }
    const current = { x: event.clientX, y: event.clientY };
    if (!shouldStartPuzzleDrag(gesture.start, current, gesture.dragging ? 0 : PUZZLE_DRAG_THRESHOLD)) return;
    if (gesture.id === null) { cancel(true); return; }
    if (!gesture.dragging) startGhost();
    if (event.cancelable) event.preventDefault();
    const g = gesture;
    g.ghost.style.transform = `translate3d(${current.x - (g.start.x - g.rect.left)}px, ${current.y - (g.start.y - g.rect.top)}px, 0)`;
    const hit = puzzleDropSlot(root, current.x, current.y);
    const target = hit && hit.slot !== null && g.stage.contains(hit.element) ? hit.element : null;
    if (target !== g.target) {
      g.target?.classList.remove("puzzle-drop-target");
      target?.classList.add("puzzle-drop-target");
      g.target = target;
    }
  }
  function up(event) {
    pointers.delete(event.pointerId);
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const g = gesture;
    if (!g.dragging) {
      const hit = doc.elementFromPoint(event.clientX, event.clientY);
      const tapped = root.contains(g.source) && (hit === g.source || g.source.contains(hit));
      cleanGesture();
      if (g.pointerType === "touch") {
        // Chromium can omit the next compatibility click for a short period
        // after a touch drag. Use the existing button click route once, then
        // swallow any native click from this same physical touch sequence.
        suppress(g.pointerId);
        if (tapped) g.source.click();
      }
      return;
    }
    if (event.cancelable) event.preventDefault();
    suppress(g.pointerId);
    const hit = root.contains(g.source) ? puzzleDropSlot(root, event.clientX, event.clientY) : null;
    const destination = hit && hit.slot !== null && g.stage.contains(hit.element) ? hit.slot : null;
    cleanGesture();
    if (destination !== null && destination !== g.sourceSlot) {
      onDrop(g.id, destination);
      onAnnounce("拼圖已放入選好的格子。");
    } else onAnnounce("這片還在原位，可以再拖一次。");
  }
  function pointerCancel(event) {
    pointers.delete(event.pointerId);
    if (gesture?.pointerId === event.pointerId) cancel(true);
  }
  function click(event) {
    if (!suppressedClick || Date.now() > suppressedClick.until || event.detail === 0 || !root.contains(event.target)) return;
    // WebKit emits the touch as pointerId 0, then its compatibility click as
    // a mouse pointer with id 1. A fresh physical pointerdown clears this
    // guard, so that translated click belongs to the touch just handled.
    if (event.pointerId !== undefined && event.pointerId !== suppressedClick.pointerId && event.pointerType !== "mouse") return;
    suppressedClick = null;
    event.preventDefault();
    event.stopImmediatePropagation();
  }
  listen(doc, "pointerdown", guardDown, true);
  listen(root, "pointerdown", down);
  listen(doc, "pointermove", move, { passive: false });
  listen(doc, "pointerup", up, true);
  listen(doc, "pointercancel", pointerCancel, true);
  listen(doc, "click", click, true);
  listen(doc, "scroll", () => cancel(true), true);
  listen(doc, "contextmenu", () => cancel(true), true);
  listen(win, "resize", () => cancel(true));
  listen(win, "blur", () => { pointers.clear(); cancel(true); });
  listen(root, "dragstart", event => { if (pieceSource(event.target)) event.preventDefault(); });
  const observer = win.MutationObserver ? new win.MutationObserver(() => {
    if (gesture && !root.contains(gesture.source)) cancel(true);
  }) : null;
  observer?.observe(root, { childList: true, subtree: true });
  return function destroy() {
    destroyed = true;
    cleanGesture();
    pointers.clear();
    suppressedClick = null;
    observer?.disconnect();
    for (const remove of listeners) remove();
  };
}
