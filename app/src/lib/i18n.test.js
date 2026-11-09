import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { LANGUAGES, MESSAGES, normalizeLanguage, translate } from "./i18n.js";

// Shared with tests/test_language.py: this function and loci.language.normalize
// must give the same answer for every case.
const SHARED = JSON.parse(
  readFileSync(new URL("../../../tests/fixtures/language-normalize.json", import.meta.url), "utf8"),
);

test("normalizeLanguage agrees with the Python normalizer on every shared case", () => {
  for (const [raw, expected] of SHARED.cases) {
    assert.equal(normalizeLanguage(raw), expected, JSON.stringify(raw));
  }
});

test("the supported languages match the server's", () => {
  assert.deepEqual(LANGUAGES, SHARED.languages);
});

test("English is the key: it returns itself, with variables filled in", () => {
  assert.equal(translate("All loci", "en"), "All loci");
  assert.equal(translate("{n} active", "en", { n: 3 }), "3 active");
});

test("Russian returns the entry and fills variables", () => {
  assert.equal(translate("Recent", "ru-RU"), "Недавние");
  assert.equal(translate("{n} active", "ru-RU", { n: 3 }), "3 активно");
});

test("a string with no entry falls back to English", () => {
  assert.equal(translate("not in the table", "ru-RU"), "not in the table");
  assert.equal(translate("toString", "ru-RU"), "toString");
});

test("an unknown placeholder is left as written", () => {
  assert.equal(translate("{n} active", "en", {}), "{n} active");
});

test("every Russian entry keeps the placeholders of its English key", () => {
  const names = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
  for (const [en, ru] of Object.entries(MESSAGES["ru-RU"])) {
    assert.deepEqual(names(ru), names(en), en);
  }
});

test("normalizeLanguage accepts the spellings people write", () => {
  assert.equal(normalizeLanguage("ru"), "ru-RU");
  assert.equal(normalizeLanguage("ru_RU"), "ru-RU");
  assert.equal(normalizeLanguage("RU-ru"), "ru-RU");
  assert.equal(normalizeLanguage("en-US"), "en");
  assert.equal(normalizeLanguage("de"), null);
  assert.equal(normalizeLanguage(undefined), null);
});
