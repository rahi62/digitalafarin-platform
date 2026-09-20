import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPrepareTakeoverRequest,
  canActivateTakeover,
  canPrepareTakeover,
  takeoverStateLabel,
} from "./takeovers.ts";

test("prepare builder accepts only an exact lowercase commit", () => {
  assert.deepEqual(
    buildPrepareTakeoverRequest("a".repeat(40)),
    { commit: "a".repeat(40) },
  );
  assert.throws(() => buildPrepareTakeoverRequest("main"));
  assert.throws(() => buildPrepareTakeoverRequest("A".repeat(40)));
});

test("only configured services can prepare controlled takeover", () => {
  assert.equal(canPrepareTakeover("adopted"), false);
  assert.equal(canPrepareTakeover("configured"), true);
  assert.equal(canPrepareTakeover("managed"), false);
});

test("only prepared takeover can activate", () => {
  assert.equal(canActivateTakeover("prepared"), true);
  assert.equal(canActivateTakeover("queued"), false);
  assert.equal(canActivateTakeover("succeeded"), false);
});

test("takeover state labels are explicit", () => {
  assert.equal(takeoverStateLabel("prepared"), "Prepared · No cutover yet");
  assert.equal(takeoverStateLabel("succeeded"), "Succeeded · Managed");
  assert.equal(takeoverStateLabel("rolled_back"), "Rolled back · Unmanaged");
  assert.equal(
    takeoverStateLabel("rollback_failed"),
    "Rollback failed · Intervention required",
  );
});
