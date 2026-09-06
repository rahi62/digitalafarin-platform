import assert from "node:assert/strict";
import test from "node:test";

import { normalizeTelegramAlias, validateTelegramAlias } from "./telegram-utils.ts";


test("normalizeTelegramAlias trims and lowercases a configured alias", () => {
  assert.equal(normalizeTelegramAlias("  SEO_News  "), "seo_news");
});

test("validateTelegramAlias accepts stable aliases and rejects arbitrary text", () => {
  assert.equal(validateTelegramAlias("seo-news"), true);
  assert.equal(validateTelegramAlias("seo channel!"), false);
  assert.equal(validateTelegramAlias(""), false);
});
