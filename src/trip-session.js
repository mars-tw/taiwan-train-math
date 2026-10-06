import { LEVELS, HISTORY_LIMITS, V15_GAME_IDS, V17_GAME_IDS, allowedGames, createTrip, seededRandom, newMemoryState } from "./engine.js?v=1.10.0";
import { newAdventureState, trackConnected } from "./adventure.js?v=1.10.0";
import { newPuzzleState } from "./puzzle.js?v=1.10.0";
import { newExplorerState } from "./explorers.js?v=1.10.0";
import { newWorkshopState, PROGRAM_DIRECTIONS, evaluateProgram, weightTotal } from "./workshop.js?v=1.10.0";
import { newDiscoveryState } from "./discovery.js?v=1.10.0";
import { journeyById } from "./journeys.js?v=1.10.0";
import { newTicketsState, ticketTotals } from "./tickets.js?v=1.10.0";

export const TRIP_SESSION_KEY = "taiwan-train-math.session.v1";
const GAME_VERSION = "1.10.0";
const MAX_BYTES = 131072;
const LEGACY_META_KEYS = ["level", "trainId", "practice", "challenge", "seed", "recentQuestions", "recentGames"];
const META_KEYS = [...LEGACY_META_KEYS, "journey", "contentVersion"];
const SNAPSHOT_KEYS = ["version", "gameVersion", "meta", "index", "solved", "assisted", "awarded", "work"];

function requireValid(condition) {
  if (!condition) throw new Error("Invalid trip session");
}
function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function exactKeys(value, keys) {
  requireValid(record(value) && Object.keys(value).length === keys.length
    && Object.keys(value).every(key => keys.includes(key)));
}
function integer(value, min = 0, max = Number.MAX_SAFE_INTEGER) {
  return Number.isSafeInteger(value) && value >= min && value <= max;
}
function array(value, length, accepts) {
  return Array.isArray(value) && value.length === length && Array.from(value).every(accepts);
}
function uniqueIndices(value, maxLength, accepts) {
  return Array.isArray(value) && value.length <= maxLength
    && Array.from(value).every(accepts) && new Set(value).size === value.length;
}
function history(value, count, length) {
  requireValid(Array.isArray(value) && value.length <= count
    && Array.from(value).every(entry => typeof entry === "string" && entry.length <= length));
  return [...value];
}
function recipe(value, legacy = false) {
  exactKeys(value, legacy ? LEGACY_META_KEYS : META_KEYS);
  requireValid(typeof value.level === "string" && Object.hasOwn(LEVELS, value.level));
  requireValid(typeof value.trainId === "string" && value.trainId.length > 0 && value.trainId.length <= 128);
  requireValid(value.practice === "mixed" || allowedGames(value.level).includes(value.practice));
  requireValid(typeof value.challenge === "boolean" && integer(value.seed, 0, 0xffffffff));
  const journey = legacy ? null : value.journey;
  const contentVersion = legacy ? "1.5.0" : value.contentVersion;
  requireValid(["1.5.0", "1.6.0", "1.7.0", "1.8.0"].includes(contentVersion));
  requireValid(value.practice === "mixed" || contentVersion === "1.8.0" ||
    (contentVersion === "1.5.0" ? V15_GAME_IDS : V17_GAME_IDS).includes(value.practice));
  requireValid(journey === null || (typeof journey === "string" && journeyById(journey) && value.practice === "mixed" && contentVersion !== "1.5.0"));
  return {
    level: value.level, trainId: value.trainId, practice: value.practice,
    challenge: value.challenge, seed: value.seed,
    recentQuestions: history(value.recentQuestions, HISTORY_LIMITS.questions, 1024),
    recentGames: history(value.recentGames, HISTORY_LIMITS.games, 64),
    journey, contentVersion,
  };
}

// Only the current activity's work is stored. Questions, free-form text,
// typed arithmetic answers and answer attempts never enter the snapshot.
function currentWork(q, trip) {
  switch (q.game) {
    case "tickets": return { game: q.game, activeTicket: trip.tickets?.activeTicket, assignments: trip.tickets?.assignments, checked: trip.tickets?.checked };
    case "program": return { game: q.game, commands: trip.workshop?.commands, checked: trip.workshop?.programChecked, shownSteps: trip.workshop?.programTrace?.length - 1 };
    case "balance": return { game: q.game, weights: trip.workshop?.weights, checked: trip.workshop?.balanceChecked };
    case "mosaic": return { game: q.game, color: trip.discovery?.mosaicColor, cells: trip.discovery?.mosaicCells };
    case "differences":
      requireValid(trip.discovery?.differencesFound instanceof Set);
      return { game: q.game, found: [...trip.discovery.differencesFound] };
    case "count":
      requireValid(trip.counted instanceof Set);
      return { game: q.game, counted: [...trip.counted] };
    case "order": return { game: q.game, order: trip.order };
    case "cargo": return { game: q.game, cargo: trip.cargo };
    case "memory": return { game: q.game, memory: trip.memory };
    case "tracks": return { game: q.game, rotations: trip.rotations };
    case "sharing": return { game: q.game, shares: trip.shares };
    case "treasure":
      requireValid(trip.found instanceof Set);
      return { game: q.game, found: [...trip.found] };
    case "puzzle": return { game: q.game, puzzle: trip.puzzle };
    case "luggage":
      return { game: q.game, luggageSelected: trip.explorer?.luggageSelected,
        luggageAssignments: trip.explorer?.luggageAssignments };
    case "maze":
      requireValid(trip.explorer?.mazeVisited instanceof Set);
      return { game: q.game, mazePosition: trip.explorer.mazePosition,
        mazeMoves: trip.explorer.mazeMoves, mazeVisited: [...trip.explorer.mazeVisited] };
    default: return { game: q.game };
  }
}
function restoreWork(q, work, trip) {
  requireValid(record(work) && work.game === q.game);
  switch (q.game) {
    case "tickets": {
      exactKeys(work, ["game", "activeTicket", "assignments", "checked"]);
      const totals = ticketTotals(q, work.assignments);
      requireValid(totals !== null && integer(work.activeTicket, 0, q.tickets.length - 1) && typeof work.checked === "boolean");
      trip.tickets = { activeTicket: work.activeTicket, assignments: [...work.assignments], checked: work.checked };
      requireValid(!trip.solved || (work.checked && totals.every((value, index) => value === q.answer[index])));
      break;
    }
    case "program": {
      const hasShownSteps = Object.hasOwn(work, "shownSteps");
      exactKeys(work, hasShownSteps ? ["game", "commands", "checked", "shownSteps"] : ["game", "commands", "checked"]);
      requireValid(Array.isArray(work.commands) && work.commands.length <= q.maxCommands && Array.from(work.commands).every(dir => typeof dir === "string" && Object.hasOwn(PROGRAM_DIRECTIONS, dir)) && typeof work.checked === "boolean");
      trip.workshop.commands = [...work.commands];
      trip.workshop.programChecked = work.checked;
      if (work.checked) {
        const result = evaluateProgram(q, work.commands);
        trip.workshop.programPosition = result.position;
        trip.workshop.programTrace = [...result.trace];
        requireValid(!hasShownSteps || work.shownSteps === result.trace.length - 1);
        requireValid(!trip.solved || result.arrived);
      } else {
        requireValid(!trip.solved);
        if (hasShownSteps) {
          requireValid(integer(work.shownSteps, 0, work.commands.length));
          const shown = evaluateProgram(q, work.commands.slice(0, work.shownSteps));
          requireValid(!shown.blocked && shown.trace.length === work.shownSteps + 1);
          trip.workshop.programPosition = shown.position;
          trip.workshop.programTrace = [...shown.trace];
        }
      }
      break;
    }
    case "balance": {
      exactKeys(work, ["game", "weights", "checked"]);
      const total = weightTotal(q, work.weights);
      requireValid(total !== null && typeof work.checked === "boolean");
      trip.workshop.weights = [...work.weights];
      trip.workshop.balanceChecked = work.checked;
      trip.workshop.balanceTilt = work.checked ? total > q.target ? -1 : total < q.target ? 1 : 0 : 0;
      requireValid(!trip.solved || (work.checked && total === q.target));
      break;
    }
    case "mosaic": {
      exactKeys(work, ["game", "color", "cells"]);
      const validColor = value => value === "empty" || q.palette.some(color => color.id === value);
      requireValid(validColor(work.color) && array(work.cells, q.columns * q.rows, validColor));
      trip.discovery.mosaicColor = work.color;
      trip.discovery.mosaicCells = [...work.cells];
      requireValid(!trip.solved || work.cells.every((value, index) => value === q.target[index]));
      break;
    }
    case "differences": {
      exactKeys(work, ["game", "found"]);
      requireValid(uniqueIndices(work.found, q.answer, value => integer(value, 0, 8) && q.differences.includes(value)));
      trip.discovery.differencesFound = new Set(work.found);
      requireValid(!trip.solved || work.found.length === q.answer);
      break;
    }
    case "count":
      exactKeys(work, ["game", "counted"]);
      requireValid(uniqueIndices(work.counted, q.count, value => integer(value, 0, q.count - 1)));
      trip.counted = new Set(work.counted);
      break;
    case "order":
      exactKeys(work, ["game", "order"]);
      requireValid(uniqueIndices(work.order, q.numbers.length, value => typeof value === "number" && q.numbers.includes(value)));
      trip.order = [...work.order];
      requireValid(!trip.solved || (work.order.length === q.answer.length && work.order.every((value, index) => value === q.answer[index])));
      break;
    case "cargo":
      exactKeys(work, ["game", "cargo"]);
      requireValid(integer(work.cargo, 0, q.max));
      trip.cargo = work.cargo;
      requireValid(!trip.solved || work.cargo === q.answer);
      break;
    case "memory": {
      exactKeys(work, ["game", "memory"]);
      exactKeys(work.memory, ["open", "matched", "turns"]);
      const { open, matched, turns } = work.memory, length = q.deck.length;
      const index = value => integer(value, 0, length - 1);
      requireValid(uniqueIndices(open, 2, index) && uniqueIndices(matched, length, index)
        && integer(turns) && open.every(value => !matched.includes(value)));
      requireValid(q.pairs.every(id => [0, 2].includes(matched.filter(at => q.deck[at] === id).length)));
      requireValid(open.length !== 2 || q.deck[open[0]] !== q.deck[open[1]]);
      trip.memory = { open: [...open], matched: [...matched], turns };
      requireValid(!trip.solved || matched.length === length);
      break;
    }
    case "tracks":
      exactKeys(work, ["game", "rotations"]);
      requireValid(array(work.rotations, q.tiles.length, value => integer(value, 0, 3)));
      trip.rotations = [...work.rotations];
      requireValid(!trip.solved || trackConnected(q, work.rotations));
      break;
    case "sharing":
      exactKeys(work, ["game", "shares"]);
      requireValid(array(work.shares, q.friends, value => integer(value, 0, q.total))
        && work.shares.reduce((sum, value) => sum + value, 0) <= q.total);
      trip.shares = [...work.shares];
      requireValid(!trip.solved || work.shares.every((value, index) => value === q.answer[index]));
      break;
    case "treasure":
      exactKeys(work, ["game", "found"]);
      requireValid(uniqueIndices(work.found, q.items.length,
        value => integer(value, 0, q.items.length - 1) && q.items[value] === q.target));
      trip.found = new Set(work.found);
      requireValid(!trip.solved || work.found.length === q.answer);
      break;
    case "puzzle": {
      exactKeys(work, ["game", "puzzle"]);
      exactKeys(work.puzzle, ["placements", "selectedPiece", "moves", "preview"]);
      const count = q.columns * q.rows, { placements, selectedPiece, moves, preview } = work.puzzle;
      requireValid(array(placements, count, value => value === null || integer(value, 0, count - 1)));
      const placed = placements.filter(value => value !== null);
      requireValid(new Set(placed).size === placed.length
        && (selectedPiece === null || integer(selectedPiece, 0, count - 1))
        && integer(moves) && typeof preview === "boolean");
      trip.puzzle = { placements: [...placements], selectedPiece, moves, preview };
      requireValid(!trip.solved || placements.every((value, index) => value === q.answer[index]));
      break;
    }
    case "luggage": {
      exactKeys(work, ["game", "luggageSelected", "luggageAssignments"]);
      const { luggageSelected: selected, luggageAssignments: assignments } = work;
      requireValid(array(assignments, q.items.length,
        value => value === null || (typeof value === "string" && q.bins.some(bin => bin.id === value))));
      requireValid(selected === null || (integer(selected, 0, q.items.length - 1) && assignments[selected] === null));
      trip.explorer.luggageSelected = selected;
      trip.explorer.luggageAssignments = [...assignments];
      requireValid(!trip.solved || assignments.every((value, index) => value === q.answer[index]));
      break;
    }
    case "maze": {
      exactKeys(work, ["game", "mazePosition", "mazeMoves", "mazeVisited"]);
      const { mazePosition: position, mazeMoves: moves, mazeVisited: visited } = work, length = q.walls.length;
      requireValid(integer(position, 0, length - 1) && integer(moves)
        && uniqueIndices(visited, length, value => integer(value, 0, length - 1))
        && visited.includes(q.start) && visited.includes(position) && moves >= visited.length - 1);
      trip.explorer.mazePosition = position;
      trip.explorer.mazeMoves = moves;
      trip.explorer.mazeVisited = new Set(visited);
      requireValid(!trip.solved || position === q.finish);
      break;
    }
    default: exactKeys(work, ["game"]);
  }
}
function initialTrip(meta, train, questions, index, solved, assisted) {
  const q = questions[index];
  return {
    meta, train, questions, index,
    attempts: 0, solved, assisted, awarded: false,
    order: [], cargo: 0, memory: newMemoryState(), memoryPeek: false,
    counted: new Set(), boardingInput: "",
    feedback: solved ? "完成了！可以繼續前往下一站。" : "",
    ...newAdventureState(q),
    puzzle: q.game === "puzzle" ? newPuzzleState(q) : null,
    explorer: ["luggage", "maze"].includes(q.game) ? newExplorerState(q) : null,
    workshop: ["program", "balance"].includes(q.game) ? newWorkshopState(q) : null,
    discovery: ["mosaic", "differences"].includes(q.game) ? newDiscoveryState(q) : null,
    tickets: q.game === "tickets" ? newTicketsState(q) : null,
  };
}

export function saveTripSession(storage, trip) {
  try {
    requireValid(record(trip) && trip.awarded === false
      && typeof trip.solved === "boolean" && typeof trip.assisted === "boolean");
    const meta = recipe(trip.meta);
    requireValid(trip.train?.id === meta.trainId);
    requireValid(Array.isArray(trip.questions) && trip.questions.length === LEVELS[meta.level].stops
      && integer(trip.index, 0, trip.questions.length - 1));
    const q = trip.questions[trip.index];
    requireValid(q?.level === meta.level && allowedGames(meta.level).includes(q.game));
    const work = currentWork(q, trip);
    restoreWork(q, work, initialTrip(meta, trip.train, trip.questions, trip.index, trip.solved, trip.assisted));
    const data = JSON.stringify({ version: 1, gameVersion: GAME_VERSION, meta,
      index: trip.index, solved: trip.solved, assisted: trip.assisted, awarded: false, work });
    requireValid(data.length <= MAX_BYTES);
    storage.setItem(TRIP_SESSION_KEY, data);
    return true;
  } catch {
    return false;
  }
}

export function readTripSession(storage, { trains } = {}) {
  try {
    const data = storage.getItem(TRIP_SESSION_KEY);
    requireValid(typeof data === "string" && data.length > 0 && data.length <= MAX_BYTES);
    const snapshot = JSON.parse(data);
    exactKeys(snapshot, SNAPSHOT_KEYS);
    requireValid(snapshot.version === 1 && [GAME_VERSION, "1.9.0", "1.8.2", "1.8.1", "1.8.0", "1.7.0", "1.6.0", "1.5.0"].includes(snapshot.gameVersion)
      && snapshot.awarded === false && typeof snapshot.solved === "boolean" && typeof snapshot.assisted === "boolean");
    const meta = recipe(snapshot.meta, snapshot.gameVersion === "1.5.0");
    requireValid(Array.isArray(trains));
    const train = trains.find(item => item.id === meta.trainId);
    requireValid(Boolean(train));
    const questions = createTrip({ level: meta.level, train, trains, practice: meta.practice,
      challenge: meta.challenge, rng: seededRandom(meta.seed),
      recentQuestions: meta.recentQuestions, recentGames: meta.recentGames,
      journey: meta.journey, contentVersion: meta.contentVersion });
    requireValid(integer(snapshot.index, 0, questions.length - 1));
    const trip = initialTrip(meta, train, questions, snapshot.index, snapshot.solved, snapshot.assisted);
    restoreWork(questions[snapshot.index], snapshot.work, trip);
    return trip;
  } catch {
    return null;
  }
}

export function clearTripSession(storage) {
  try {
    storage.removeItem(TRIP_SESSION_KEY);
    return true;
  } catch {
    return false;
  }
}
