import assert from "node:assert/strict";
import test from "node:test";
import { classifyGscRegistryFailure } from "./gsc-registry.js";

test("revoked Google refresh credentials require reauthorization", () => {
  const error = classifyGscRegistryFailure({
    status: 401,
    code: "gsc_reauthorization_required",
    error: "Google authorization is no longer valid. Reconnect Search Console.",
  });

  assert.equal(error.code, "gsc_reauthorization_required");
  assert.equal(error.status, 401);
});

test("transient token exchange failures remain distinguishable", () => {
  const error = classifyGscRegistryFailure({
    status: 502,
    code: "gsc_refresh_failed",
    error: "Unable to refresh Google authorization.",
  });

  assert.equal(error.code, "gsc_refresh_failed");
  assert.equal(error.status, 502);
});
