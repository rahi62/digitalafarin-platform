import assert from "node:assert/strict";
import test from "node:test";

import { buildDeployRequest, projectPath } from "./deployments.ts";

test("buildDeployRequest distinguishes latest and exact commit without commands", () => {
  assert.deepEqual(buildDeployRequest(), {});
  assert.deepEqual(buildDeployRequest("a".repeat(40)), { commit: "a".repeat(40) });
  assert.throws(() => buildDeployRequest("main; id"));
});

test("projectPath encodes external UUID-like identity", () => {
  assert.equal(projectPath("project/id"), "/api/control/v1/projects/project%2Fid/");
});
