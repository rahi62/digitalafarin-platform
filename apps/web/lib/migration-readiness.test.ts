import assert from "node:assert/strict";
import test from "node:test";

import { deriveMigrationReadiness } from "./migration-readiness.ts";

test("readiness derives ordered resource-backed migration steps", () => {
  const steps = deriveMigrationReadiness(
    [{ id: "server", status: "online" }],
    [{
      services: [{ id: "backend" }, { id: "frontend" }],
      variables: [{ id: "secret", value_type: "secret", has_value: true }],
      volumes: [{ id: "media" }],
      databases: [{ id: "db", status: "ready" }],
      domains: [{ id: "domain", status: "configured", ssl_enabled: true }],
    }],
    {
      operations: [{ server_id: "server", kind: "server.bootstrap", state: "succeeded" }],
      deployments: [
        { service_id: "backend", state: "succeeded" },
        { service_id: "frontend", state: "succeeded" },
      ],
      metrics: [{ id: "server", disk_percent: 20, stale: false }],
    },
  );

  assert.equal(steps[0].label, "Enroll new VPS");
  assert.equal(steps[0].state, "ready");
  assert.equal(steps[1].label, "Heartbeat");
  assert.equal(steps[1].state, "ready");
  assert.equal(steps.find((step) => step.label === "Deploy backend")?.state, "ready");
  assert.equal(steps.find((step) => step.label === "SSL")?.state, "ready");
  assert.equal(steps.at(-1)?.label, "DNS cutover");
});

test("readiness uses completed bootstrap and deployments instead of configuration alone", () => {
  const steps = deriveMigrationReadiness(
    [{ id: "server", status: "online" }],
    [{
      services: [
        { id: "backend", runtime: "python-django" },
        { id: "frontend", runtime: "node-nextjs" },
      ],
      variables: [{ id: "secret", value_type: "secret", has_value: true }],
      volumes: [{ id: "media" }],
      databases: [{ id: "db", status: "ready" }],
      domains: [{ id: "domain", status: "configured", ssl_enabled: true }],
    }],
    {
      operations: [{ server_id: "server", kind: "server.bootstrap", state: "succeeded" }],
      deployments: [
        { service_id: "backend", state: "succeeded" },
        { service_id: "frontend", state: "succeeded" },
      ],
      metrics: [{ id: "server", disk_percent: 85, stale: false }],
    },
  );

  assert.equal(steps.find((step) => step.label === "Bootstrap")?.state, "ready");
  assert.equal(steps.find((step) => step.label === "Deploy backend")?.state, "ready");
  assert.equal(steps.find((step) => step.label === "Deploy frontend")?.state, "ready");
  assert.equal(steps.find((step) => step.label === "Health check")?.state, "ready");
  assert.equal(steps.find((step) => step.label === "Disk guardrail")?.state, "warning");
});

test("readiness blocks failed bootstrap and stale or full disk telemetry", () => {
  const steps = deriveMigrationReadiness(
    [{ id: "server", status: "online" }],
    [{ services: [{ id: "backend", runtime: "python-django" }] }],
    {
      operations: [{ server_id: "server", kind: "server.bootstrap", state: "failed" }],
      deployments: [],
      metrics: [{ id: "server", disk_percent: 90, stale: false }],
    },
  );

  assert.equal(steps.find((step) => step.label === "Bootstrap")?.state, "blocked");
  assert.equal(steps.find((step) => step.label === "Deploy backend")?.state, "pending");
  assert.equal(steps.find((step) => step.label === "Disk guardrail")?.state, "blocked");
});
