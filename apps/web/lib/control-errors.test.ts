import assert from "node:assert/strict";
import test from "node:test";
import { describeControlError } from "./control-errors.ts";

test("shows field validation errors from Control Plane", () => {
  assert.equal(describeControlError(400, { name: ["This field may not be blank."], slug: ["Already exists."] }), "name: This field may not be blank.; slug: Already exists.");
});

test("shows dependency counts on conflict", () => {
  assert.equal(describeControlError(409, { message: "Project cannot be deleted.", blockers: { services: 2, volumes: 1 } }), "Project cannot be deleted. Blockers: 2 services, 1 volume.");
});

test("does not expose arbitrary response values", () => {
  assert.equal(describeControlError(500, { token: "private", detail: "server error" }), "Control Plane returned HTTP 500");
});

test("provides a readable code when the API has no message", () => {
  assert.equal(describeControlError(409, { error: "server_offline" }), "Server offline.");
});
