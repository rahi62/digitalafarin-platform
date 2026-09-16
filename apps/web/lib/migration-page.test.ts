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
