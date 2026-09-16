import assert from "node:assert/strict";
import test from "node:test";

import { buildBootstrapOperation, buildProjectCreate } from "./migration-actions.ts";

test("buildBootstrapOperation emits fixed empty payload and idempotency key", () => {
  assert.deepEqual(
    buildBootstrapOperation("server-id", "bootstrap-1"),
    {
      server_id: "server-id",
      kind: "server.bootstrap",
      payload: {},
      idempotency_key: "bootstrap-1",
    },
  );
});

test("buildProjectCreate trims operator input and rejects unsafe slug", () => {
  assert.deepEqual(buildProjectCreate("  Oily  ", " oily "), { name: "Oily", slug: "oily" });
  assert.throws(() => buildProjectCreate("Oily", "oily/../../etc"));
  assert.throws(() => buildProjectCreate(" ", "oily"));
});
