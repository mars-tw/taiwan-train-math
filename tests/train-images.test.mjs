import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { createHash } from "node:crypto";
import { verifiedPhoto, displayTrain, trainImage, samePhotoIdentity, photoGameTrains, puzzlePhotoTrains, photoLabel } from "../src/train-images.js";
import { questionFor, seededRandom } from "../src/engine.js";
import { normalizePhotoRecord, hasCompletePhotoCredit, renderPhotoCreditDocuments, photoCreditDocuments } from "../scripts/photo-credits.mjs";

const readJson = path => JSON.parse(readFileSync(new URL(`../${path}`, import.meta.url), "utf8"));
const catalogue = readJson("data/trains.json"), trains = catalogue.trains;
const manifests = ["tra", "special", "tourism"].map(name => readJson(`data/train-photos-${name}.json`));
const records = manifests.flatMap(value => Array.isArray(value) ? value : value.photos).map(normalizePhotoRecord);
const byId = id => trains.find(train => train.id === id);
const legacyGroups = {
  hero: ["700t"], emu3000: ["emu3000"], temu1000: ["temu1000"], temu2000: ["temu2000"],
  e1000: ["e1000"], emu900: ["emu900"], emu800: ["emu800"], emu700: ["emu700"],
  commuter: ["emu600", "emu500"], e500: ["e500"], "electric-loco": ["e200", "e300", "e400"],
  r200: ["r200"], "classic-loco": ["r20", "r100", "r150", "r180", "r190", "juguang"],
  "diesel-railcar": ["dr1000", "drc1000"], dr3100: ["dr3100"], switcher: ["dhl100", "dl2500"],
  alishan: ["forest-dl25-30", "forest-dl31-34", "forest-dl38", "forest-dl39-43", "forest-dl45-51"],
  shay: ["shay-21", "shay-25", "shay-26", "shay-31"], "tourism-blue": ["breezy-blue"],
  "tourism-black": ["future-express", "future-kitchen", "island-star"],
  "tourism-green": ["sea-breeze", "mountain-mist"], "tourism-forest": ["formosensis", "vivid-express", "cypress-coach"],
  sugar: ["xihu", "suantou", "wushulin", "xinying", "qiaotou"], "sugar-steam": ["sugar-346", "ck124", "ck101", "ldk59"],
  e5: ["e5"], n700s: ["n700s", "n700st"], maglev: ["l0"], "steam-main": ["ct273", "dt668"],
};

test("all 59 legacy image identities remain intact alongside the new reference layer", () => {
  const expected = Object.fromEntries(Object.entries(legacyGroups).flatMap(([image, ids]) => ids.map(id => [id, `assets/images/${image}.webp`])));
  assert.equal(Object.keys(expected).length, 59);
  assert.deepEqual(Object.fromEntries(trains.map(train => [train.id, train.image])), expected);
  for (const train of trains) {
    assert.ok(existsSync(new URL(`../${train.image}`, import.meta.url)));
    assert.equal(trainImage(train, "1.5.0"), expected[train.id]);
    assert.equal(trainImage(train, "1.6.0"), expected[train.id]);
  }
});
test("every verified reference matches its actual file hash, source, licence and author", () => {
  assert.equal(records.length, 59);
  assert.equal(new Set(records.map(row => row.id)).size, 59);
  const verified = records.filter(hasCompletePhotoCredit);
  assert.equal(verified.length, 58);
  for (const row of records) {
    const train = byId(row.id); assert.ok(train, row.id);
    if (!hasCompletePhotoCredit(row)) {
      assert.equal(verifiedPhoto(train), null, row.id);
      assert.equal(trainImage(train), null, row.id);
      continue;
    }
    const photo = verifiedPhoto(train); assert.ok(photo, row.id);
    for (const field of ["path", "sourceUrl", "thumbnailUrl", "licenseName", "licenseUrl", "author", "sha256", "modelEvidence"])
      assert.equal(photo[field], row[field], `${row.id}: ${field}`);
    const bytes = readFileSync(new URL(`../${photo.path}`, import.meta.url));
    assert.equal(createHash("sha256").update(bytes).digest("hex"), row.sha256, row.id);
    assert.ok(["exterior", "interior"].includes(photo.view), row.id);
    assert.match(row.sourceUrl, /^https:\/\/commons\.wikimedia\.org\/wiki\/File:/);
    assert.match(row.licenseUrl, /^https?:\/\//);
    assert.doesNotMatch(row.author, /<[^>]*>|javascript:/i);
    assert.ok(row.modelEvidence.length > 10, row.id);
    assert.equal(trainImage(train), row.path);
    if (row.canonicalModel) assert.equal(photo.canonicalModel, row.canonicalModel, row.id);
  }
  assert.equal(byId("emu600").referencePhoto.path, "assets/images/real-emu600.jpg");
  assert.match(byId("emu600").referencePhoto.modelEvidence, /EMC614/);
  assert.match(byId("e500").referencePhoto.modelEvidence, /E514/);
});
test("photo games exclude pending, interior and non-operating trains and collapse DR aliases", () => {
  const pool = photoGameTrains(trains);
  assert.equal(pool.length, 54);
  for (const train of pool) {
    assert.equal(train.referencePhoto.view, "exterior");
    assert.equal(train.referencePhoto.status, "verified");
    assert.notEqual(train.status, "future");
    assert.equal(train.image, train.referencePhoto.path);
    assert.notEqual(train.image, byId(train.id).image);
  }
  for (const excluded of ["ldk59", "future-kitchen", "vivid-express", "n700st"])
    assert.ok(!pool.some(train => train.id === excluded), excluded);
  assert.equal(pool.filter(train => ["dr1000", "drc1000"].includes(train.id)).length, 1);
  assert.equal(byId("dr1000").canonicalModel, "DR1000");
  assert.equal(byId("drc1000").canonicalModel, "DR1000");
  assert.equal(samePhotoIdentity(byId("dr1000"), byId("drc1000")), true);
  for (const id of ["emu500", "emu600", "e200", "e300", "e400"])
    assert.ok(pool.some(train => train.id === id), `${id}: shared old artwork must not collapse different real vehicle types`);
});
test("display corrections leave historical catalogue text unchanged and labelled references honest", () => {
  const old = byId("drc1000"); const displayed = displayTrain(old);
  assert.equal(old.model, "DRC1000"); assert.equal(displayed.model, old.displayModel);
  assert.equal(displayed.image, old.image); assert.equal(displayed.referencePhoto, old.referencePhoto);
  assert.equal(photoLabel(byId("future-kitchen")), "實車內裝照片");
  assert.equal(photoLabel(byId("vivid-express")), "實車內裝照片");
  assert.equal(photoLabel(byId("n700st")), "抵台實車・尚未營運");
  assert.equal(photoLabel(byId("ldk59")), "正確實車照片待補");
  assert.equal(displayTrain(byId("suantou")).name, "蒜頭五分車");
});

test("puzzles use full landscape photos with distinguishable pieces while portrait E1000 remains recognisable", () => {
  const pool = puzzlePhotoTrains(trains);
  assert.equal(pool.length, 53);
  assert.ok(!pool.some(t => t.id === "e1000"));
  assert.ok(photoGameTrains(trains).some(t => t.id === "e1000"));
  assert.equal(trainImage(byId("e1000")), "assets/images/real-e1000.jpg");
  for (const level of ["small", "medium", "large"]) for (let seed = 0; seed < 32; seed++) {
    const q = questionFor({ level, game: "puzzle", train: byId("e1000"), trains,
      rng: seededRandom(Math.imul(seed + 1, 2654435761)) });
    assert.ok(pool.some(t => t.id === q.target && t.image === q.image));
  }
});
test("missing or unsafe references cannot masquerade as a verified real image", () => {
  const train = byId("emu3000"), photo = train.referencePhoto;
  for (const patch of [
    { status: "pending" }, { author: "" }, { licenseName: "" }, { licenseUrl: "" },
    { licenseUrl: "javascript:alert(1)" }, { sourceUrl: "" }, { sourceUrl: "http://example.com/file" },
    { path: "assets/images/emu3000.webp" }, { path: "https://example.com/other.jpg" },
    { path: "assets/images/../real-emu3000.jpg" },
  ]) {
    const bad = { ...train, referencePhoto: { ...photo, ...patch } };
    assert.equal(verifiedPhoto(bad), null, JSON.stringify(patch));
    assert.equal(trainImage(bad), null);
    assert.equal(trainImage(bad, "1.6.0"), train.image);
  }
  assert.equal(verifiedPhoto(null), null);
  assert.equal(verifiedPhoto({ ...train, referencePhoto: undefined }), null);
});
test("identification questions use real exteriors without same-family or mechanical-type distractors", () => {
  const pool = photoGameTrains(trains), chosen = byId("700t"), seen = new Set();
  for (let seed = 0; seed < 180; seed++) {
    const q = questionFor({ level: "large", game: "identify", train: chosen, trains, rng: seededRandom(Math.imul(seed + 1, 2654435761)), contentVersion: "1.7.0" });
    const target = pool.find(train => train.id === q.target); assert.ok(target);
    assert.equal(q.choices.length, 3); assert.equal(new Set(q.choices).size, 3);
    for (const id of q.choices.filter(id => id !== q.target)) {
      const other = pool.find(train => train.id === id); assert.ok(other);
      assert.equal(samePhotoIdentity(target, other), false);
      if (target.modelKind === "type") assert.notEqual(other.referencePhoto.vehicleModel, target.model);
    }
    seen.add(target.id);
  }
  assert.ok(seen.size > 40);
});
test("credits preserve the original AI licence and each third-party licence without granting pending rights", async () => {
  const first = await photoCreditDocuments(), second = await photoCreditDocuments();
  assert.equal(first.assetLicense, second.assetLicense);
  assert.equal(first.photoCredits, second.photoCredits);
  assert.equal(first.verified, 58); assert.equal(first.pending, 1);
  assert.equal(readFileSync(new URL("../ASSET-LICENSE.md", import.meta.url), "utf8"), first.assetLicense);
  assert.equal(readFileSync(new URL("../docs/train-photo-credits.md", import.meta.url), "utf8"), first.photoCredits);
  assert.match(first.assetLicense, /31 張 AI 情境插圖/);
  assert.match(first.assetLicense, /mars-tw／小小列車長/);
  assert.match(first.assetLicense, /不重新授權|沒有改授權/);
  assert.doesNotMatch(first.assetLicense, /專案未下載或再散布官方網頁照片/);
  for (const row of records.filter(hasCompletePhotoCredit)) {
    assert.ok(first.photoCredits.includes(row.sha256), row.id);
    assert.ok(first.photoCredits.includes(row.licenseName), row.id);
    assert.ok(first.photoCredits.includes(row.path), row.id);
  }
  const pendingSection = first.photoCredits.split("## 待補條目")[1].split("## 清單與重建")[0];
  assert.match(pendingSection, /`ldk59`/); assert.doesNotMatch(pendingSection, /CC BY 4\.0|CC0|Public domain/);
});
test("credit generation degrades a supposedly verified but unlicensed record to the pending table", () => {
  const row = records.find(row => row.id === "emu3000");
  const bad = { ...row, author: "<b>Photographer</b>", licenseName: "", licenseUrl: "" };
  const result = renderPhotoCreditDocuments({
    catalogue: { reviewed: "2026-10-05", trains: [byId("emu3000")] },
    artwork: readJson("assets/manifest.json"), manifests: [{ photos: [bad] }],
  });
  assert.equal(result.verified, 0); assert.equal(result.pending, 1);
  assert.match(result.photoCredits, /授權或來源資料不完整/);
  assert.doesNotMatch(result.photoCredits, /<b>|原始縮圖/);
  assert.equal(normalizePhotoRecord(bad).author, "Photographer");
});
