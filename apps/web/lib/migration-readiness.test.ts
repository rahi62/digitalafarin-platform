import assert from "node:assert/strict";
import test from "node:test";

import { deriveMigrationReadiness } from "./migration-readiness.ts";

test("readiness derives ordered resource-backed migration steps", () => {
  const steps = deriveMigrationReadiness(
    [{ id: "server", status: "online" }],
    [{
      services: [
        { id: "backend", runtime: "python-django", target_server_id: "server" },
        { id: "frontend", runtime: "node-nextjs", target_server_id: "server" },
      ],
      variables: [{ id: "secret", value_type: "secret", has_value: true }],
      volumes: [{ id: "media" }],
      databases: [{ id: "db", status: "ready" }],
      domains: [{ id: "domain", status: "configured", ssl_enabled: true }],
    }],
    {
      operations: [{ server_id: "server", kind: "server.bootstrap", state: "succeeded", created_at: "2026-09-16T08:00:00Z" }],
      deployments: [
        { service_id: "backend", state: "succeeded", queued_at: "2026-09-16T08:00:00Z" },
        { service_id: "frontend", state: "succeeded", queued_at: "2026-09-16T08:00:00Z" },
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
        { id: "backend", runtime: "python-django", target_server_id: "server" },
        { id: "frontend", runtime: "node-nextjs", target_server_id: "server" },
      ],
      variables: [{ id: "secret", value_type: "secret", has_value: true }],
      volumes: [{ id: "media" }],
      databases: [{ id: "db", status: "ready" }],
      domains: [{ id: "domain", status: "configured", ssl_enabled: true }],
    }],
    {
      operations: [{ server_id: "server", kind: "server.bootstrap", state: "succeeded", created_at: "2026-09-16T08:00:00Z" }],
      deployments: [
        { service_id: "backend", state: "succeeded", queued_at: "2026-09-16T08:00:00Z" },
        { service_id: "frontend", state: "succeeded", queued_at: "2026-09-16T08:00:00Z" },
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
    [{ services: [{ id: "backend", runtime: "python-django", target_server_id: "server" }] }],
    {
      operations: [{ server_id: "server", kind: "server.bootstrap", state: "failed", created_at: "2026-09-16T08:00:00Z" }],
      deployments: [],
      metrics: [{ id: "server", disk_percent: 90, stale: false }],
    },
  );

  assert.equal(steps.find((step) => step.label === "Bootstrap")?.state, "blocked");
  assert.equal(steps.find((step) => step.label === "Deploy backend")?.state, "pending");
  assert.equal(steps.find((step) => step.label === "Disk guardrail")?.state, "blocked");
});

test("readiness blocks a service whose newest deployment failed after an older success", () => {
  const steps = deriveMigrationReadiness(
    [{ id: "server", status: "online" }],
    [{ services: [{ id: "backend", runtime: "python-django", target_server_id: "server" }] }],
    {
      operations: [{ server_id: "server", kind: "server.bootstrap", state: "succeeded", created_at: "2026-09-16T08:00:00Z" }],
      deployments: [
        { service_id: "backend", state: "succeeded", queued_at: "2026-09-16T08:00:00Z" },
        { service_id: "backend", state: "failed", queued_at: "2026-09-16T09:00:00Z" },
      ],
      metrics: [{ id: "server", disk_percent: 20, stale: false }],
    },
  );

  assert.equal(steps.find((step) => step.label === "Deploy backend")?.state, "blocked");
  assert.equal(steps.find((step) => step.label === "Health check")?.state, "blocked");
});

test("readiness correlates bootstrap state to each service target server", () => {
  const steps = deriveMigrationReadiness(
    [
      { id: "target", status: "online" },
      { id: "unrelated", status: "online" },
    ],
    [{ services: [{ id: "backend", runtime: "python-django", target_server_id: "target" }] }],
    {
      operations: [
        { server_id: "unrelated", kind: "server.bootstrap", state: "succeeded", created_at: "2026-09-16T10:00:00Z" },
        { server_id: "target", kind: "server.bootstrap", state: "failed", created_at: "2026-09-16T09:00:00Z" },
      ],
      deployments: [],
      metrics: [
        { id: "target", disk_percent: 20, stale: false },
        { id: "unrelated", disk_percent: 20, stale: false },
      ],
    },
  );

  assert.equal(steps.find((step) => step.label === "Bootstrap")?.state, "blocked");
});
