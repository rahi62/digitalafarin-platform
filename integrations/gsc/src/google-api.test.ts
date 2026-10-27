import test from "node:test";
import assert from "node:assert/strict";
import { propertyUrl, READONLY_SCOPE } from "./google-api.js";

test("restricts OAuth scope to Google Search Console read-only", () => {
  assert.equal(READONLY_SCOPE, "https://www.googleapis.com/auth/webmasters.readonly");
});
test("supports domain properties", () => {
  assert.equal(propertyUrl("sc-domain:example.com"), "sc-domain%3Aexample.com");
});
test("rejects non-property identifiers", () => {
  assert.throws(() => propertyUrl("file:///etc/passwd"));
});
