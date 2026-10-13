import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createParentChallenge, matchesParentChallenge, classifyNativeResourceLink } from "../src/native-parent-access.js";
import { photoCreditsMarkup, trainSourceLinkMarkup, parentResourcesMarkup } from "../src/parent-resources.js";
import { discoveryMarkup } from "../src/learning-ui.js";
import { LEARNING_SOURCES } from "../src/learning-content.js";
import { verifiedPhoto } from "../src/train-images.js";

const base = "capacitor://localhost/index.html";
const documents = { "PRIVACY.md": "local privacy", "docs/train-photo-credits.md": "local credits" };
const { trains } = JSON.parse(readFileSync(new URL("../data/trains.json", import.meta.url), "utf8"));

test("the adult challenge grants access only for the generated result and fails closed without randomness", () => {
  const challenge = createParentChallenge(values => { values[0] = 16; values[1] = 3; return values; });
  assert.deepEqual({ ...challenge }, { first: 29, second: 9 });
  assert.equal(matchesParentChallenge(challenge, "261"), true);
  for (const answer of ["260", "2610", "", "29", 261]) assert.equal(matchesParentChallenge(challenge, answer), false);
  for (const random of [null, () => {}, () => { throw Error("random unavailable"); }]) assert.equal(createParentChallenge(random), null);
  assert.equal(matchesParentChallenge({ first: 0, second: 0 }, "0"), false);
});

test("native navigation requires an open authorized parent area and a safe destination", () => {
  const parent = { authorized: true, inParentArea: true };
  for (const href of ["https://example.org/credits", "PRIVACY.md", "docs/train-photo-credits.md"]) {
    assert.deepEqual(classifyNativeResourceLink(href, base, documents, { ...parent, authorized: false }), { kind: "blocked" });
    assert.deepEqual(classifyNativeResourceLink(href, base, documents, { ...parent, inParentArea: false }), { kind: "blocked" });
  }
  assert.deepEqual(classifyNativeResourceLink("PRIVACY.md", base, documents, parent), { kind: "document", url: "PRIVACY.md" });
  assert.deepEqual(classifyNativeResourceLink("https://example.org/credits", base, documents, parent), { kind: "external", url: "https://example.org/credits" });
  for (const href of ["support.html", "https://localhost/fake", "javascript:alert(1)", "http://example.org/", "//example.org/", "file:///etc/passwd", "#game"]) {
    assert.deepEqual(classifyNativeResourceLink(href, base, documents, parent), { kind: "blocked" }, href);
  }
});

test("native child views keep photo attribution and facts without external anchors; web links remain", () => {
  const train = trains.find(item => verifiedPhoto(item) && item.sources.length);
  const photo = verifiedPhoto(train);
  const nativeCredit = photoCreditsMarkup(photo, { native: true });
  assert.match(nativeCredit, new RegExp(photo.author));
  assert.match(nativeCredit, new RegExp(photo.licenseName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.doesNotMatch(nativeCredit + trainSourceLinkMarkup(train, { native: true }), /<a\b|href=/);
  assert.match(photoCreditsMarkup(photo), /原始照片 ↗/);
  assert.match(trainSourceLinkMarkup(train), /資料來源 ↗/);
  const fact = { kind: "train", text: "列車的名字。", sources: [{ title: "資料", url: "https://example.org/" }] };
  assert.doesNotMatch(discoveryMarkup(fact, { native: true }), /<a\b|href=/);
  assert.match(discoveryMarkup(fact), /href="https:\/\/example.org\/"/);
});

test("the gated parent area retains every catalogue source, verified photo credit and learning source", () => {
  const markup = parentResourcesMarkup(trains, LEARNING_SOURCES, { verifiedPhoto });
  const parent = { authorized: true, inParentArea: true };
  for (const train of trains) {
    for (const url of train.sources) {
      assert.ok(markup.includes(url.replaceAll("&", "&amp;")), `${train.id}: ${url}`);
      assert.equal(classifyNativeResourceLink(url, base, documents, parent).kind, "external", `${train.id}: ${url}`);
    }
    const photo = verifiedPhoto(train);
    if (photo) {
      assert.ok(markup.includes(photo.author.replaceAll("&", "&amp;")), train.id);
      assert.ok(markup.includes(photo.sourceUrl.replaceAll("&", "&amp;")), train.id);
      assert.ok(markup.includes(photo.licenseUrl.replaceAll("&", "&amp;")), train.id);
      assert.equal(classifyNativeResourceLink(photo.sourceUrl, base, documents, parent).kind, "external", train.id);
      assert.equal(classifyNativeResourceLink(photo.licenseUrl, base, documents, parent).kind, "external", train.id);
    }
  }
  for (const source of Object.values(LEARNING_SOURCES)) {
    assert.ok(markup.includes(source.url.replaceAll("&", "&amp;")), source.id);
    assert.equal(classifyNativeResourceLink(source.url, base, documents, parent).kind, "external", source.id);
  }
});
