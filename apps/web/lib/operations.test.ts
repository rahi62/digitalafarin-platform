import assert from "node:assert/strict";
import test from "node:test";

import { buildServiceOperation } from "./operations.ts";

test("buildServiceOperation emits only the typed service payload", () => {
  assert.deepEqual(
    buildServiceOperation("server-id", "restart", "oily-api.service", "request-1"),
    {
      server_id: "server-id",
      kind: "service.restart",
      payload: { unit_name: "oily-api.service" },
      idempotency_key: "request-1",
    },
  );
});

test("buildServiceOperation rejects arbitrary actions and invalid units", () => {
  assert.throws(() => buildServiceOperation("server-id", "reload" as "restart", "oily-api.service", ""));
  assert.throws(() => buildServiceOperation("server-id", "start", "api.service; id", ""));
});
