import assert from "node:assert/strict";
import test from "node:test";

import { formatAge, formatUptime, statusTone, summarizeServices } from "./dashboard.ts";

const services = [
  { unit_name: "api.service", description: "API", load_state: "loaded", active_state: "active", sub_state: "running", last_seen_at: "2026-09-02T09:00:00Z" },
  { unit_name: "deploy.service", description: "Deploy", load_state: "loaded", active_state: "failed", sub_state: "failed", last_seen_at: "2026-09-02T09:00:00Z" },
  { unit_name: "backup.service", description: "Backup", load_state: "loaded", active_state: "inactive", sub_state: "dead", last_seen_at: "2026-09-02T09:00:00Z" },
];

test("formatUptime returns Persian day/hour summary", () => {
  assert.equal(formatUptime(183600), "۲ روز و ۳ ساعت");
});

test("formatAge maps recent and old snapshots to concise Persian labels", () => {
  assert.equal(formatAge(11), "۱۱ ثانیه پیش");
  assert.equal(formatAge(75), "۱ دقیقه پیش");
  assert.equal(formatAge(7200), "۲ ساعت پیش");
  assert.equal(formatAge(null), "بدون داده");
});

test("summarizeServices separates running failed and inactive services", () => {
  assert.deepEqual(summarizeServices(services), {
    total: 3,
    active: 1,
    failed: 1,
    inactive: 1,
    unhealthy: 2,
  });
});

test("statusTone maps operational states consistently", () => {
  assert.equal(statusTone("online"), "success");
  assert.equal(statusTone("active"), "success");
  assert.equal(statusTone("stale"), "warning");
  assert.equal(statusTone("inactive"), "warning");
  assert.equal(statusTone("offline"), "danger");
  assert.equal(statusTone("failed"), "danger");
  assert.equal(statusTone("something-else"), "neutral");
});
