import { describe, expect, it } from "vitest";
import {
  approvalStatusEnum,
  executionStatusEnum,
  projectStatusEnum,
  riskLevelEnum,
  taskStatusEnum,
} from "./schema.js";

describe("Agency Core database schema", () => {
  it("keeps the existing project lifecycle states", () => {
    expect(projectStatusEnum.enumValues).toEqual(["active", "paused", "archived"]);
  });

  it("keeps the existing task lifecycle states", () => {
    expect(taskStatusEnum.enumValues).toEqual(["todo", "doing", "done", "blocked"]);
  });

  it("defines explicit operational risk levels", () => {
    expect(riskLevelEnum.enumValues).toEqual(["low", "medium", "high", "critical"]);
  });

  it("separates approval state from execution state", () => {
    expect(approvalStatusEnum.enumValues).toEqual(["pending", "approved", "rejected", "expired", "cancelled"]);
    expect(executionStatusEnum.enumValues).toEqual(["queued", "running", "succeeded", "failed", "cancelled"]);
  });
});
