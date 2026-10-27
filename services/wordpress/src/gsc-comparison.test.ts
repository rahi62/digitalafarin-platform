import test from "node:test";
import assert from "node:assert/strict";
import { compareGscRows } from "./gsc-comparison.js";

test("compares overlapping and newly appearing GSC pages by dimension key", () => {
  const previous = { rows: [
    { keys: ["https://example.com/a"], clicks: 30, impressions: 200, ctr: 0.15, position: 3 },
    { keys: ["https://example.com/b"], clicks: 5, impressions: 50, ctr: 0.1, position: 7 },
  ] };
  const current = { rows: [
    { keys: ["https://example.com/a"], clicks: 12, impressions: 120, ctr: 0.1, position: 8 },
    { keys: ["https://example.com/c"], clicks: 9, impressions: 90, ctr: 0.1, position: 6 },
  ] };
  const rows = compareGscRows(previous, current);
  const a = rows.find((r) => r.keys[0].endsWith("/a"));
  assert.ok(a);
  assert.equal(a.delta.clicks, -18);
  assert.equal(a.delta.impressions, -80);
  assert.ok(Math.abs(a.delta.ctrPercentagePoints + 5) < 1e-9);
  assert.equal(a.delta.position, 5);
  assert.equal(rows.find((r) => r.keys[0].endsWith("/b"))?.current, null);
  assert.equal(rows.find((r) => r.keys[0].endsWith("/c"))?.previous, null);
});
