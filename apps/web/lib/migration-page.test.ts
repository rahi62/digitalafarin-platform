import assert from "node:assert/strict";
import test from "node:test";

import { loadMigrationReadiness } from "./migration-page.ts";

test("migration route converts an unavailable server metric into blocked stale readiness", async () => {
  const steps = await loadMigrationReadiness({
    listServers: async () => [
      { id: "online", status: "online" },
      { id: "offline", status: "offline" },
    ],
    listProjects: async () => [{ id: "project" }],
    getProject: async () => ({
      services: [{ id: "backend", runtime: "python-django", target_server_id: "offline" }],
    }),
    listOperations: async () => [],
    getMetrics: async (serverId) => {
      if (serverId === "offline") throw new Error("metrics unavailable");
      return { id: serverId, disk_percent: 20, stale: false };
    },
    listDeployments: async () => [],
  });

  assert.equal(steps.find((step) => step.label === "Heartbeat")?.state, "blocked");
  assert.equal(steps.find((step) => step.label === "Disk guardrail")?.state, "blocked");
  assert.equal(
    steps.find((step) => step.label === "Disk guardrail")?.detail,
    "Disk telemetry is missing or stale",
  );
});

test("migration readiness can scope resource checks to the selected project", async () => {
  const loaded: string[] = [];
  const steps = await loadMigrationReadiness({
    listServers: async () => [{ id: "server", status: "online" }],
    listProjects: async () => [{ id: "one" }, { id: "two" }],
    getProject: async (projectId) => {
      loaded.push(projectId);
      return projectId === "two"
        ? { services: [{ id: "backend", runtime: "python-django", target_server_id: "server" }] }
        : { services: [] };
    },
    listOperations: async () => [{ server_id: "server", kind: "server.bootstrap", state: "succeeded", created_at: "2026-09-16T10:00:00Z" }],
    getMetrics: async (serverId) => ({ id: serverId, disk_percent: 20, stale: false }),
    listDeployments: async () => [],
  }, "two");

  assert.deepEqual(loaded, ["two"]);
  assert.equal(steps.find((step) => step.label === "Select project")?.state, "ready");
  assert.match(steps.find((step) => step.label === "Select project")?.detail ?? "", /selected/i);
});
