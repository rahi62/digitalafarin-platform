import { describe, expect, it } from "vitest";
import { approvalAuthorizesExecution, executionRequiresApproval } from "./policy.js";

describe("Execution authorization policy", () => {
  it("requires approval for protected action types even when a task is low-risk", () => {
    expect(executionRequiresApproval({ riskLevel: "low", taskApprovalRequired: false, actionType: "redirect" })).toBe(true);
    expect(executionRequiresApproval({ riskLevel: "low", taskApprovalRequired: false, actionType: "content_analysis" })).toBe(false);
  });

  it("requires approval for medium, high and critical execution risk", () => {
    expect(executionRequiresApproval({ riskLevel: "medium", taskApprovalRequired: false, actionType: "content_update" })).toBe(true);
    expect(executionRequiresApproval({ riskLevel: "high", taskApprovalRequired: false, actionType: "content_update" })).toBe(true);
    expect(executionRequiresApproval({ riskLevel: "critical", taskApprovalRequired: false, actionType: "content_update" })).toBe(true);
  });

  it("binds an approval to the exact project, task, action and integration", () => {
    const approval = {
      projectId: "project-1",
      taskId: "task-1",
      actionType: "content_update",
      integrationConnectionId: "integration-1",
      status: "approved" as const,
    };

    expect(
      approvalAuthorizesExecution(approval, {
        projectId: "project-1",
        taskId: "task-1",
        actionType: "content_update",
        integrationConnectionId: "integration-1",
      }),
    ).toBe(true);

    expect(
      approvalAuthorizesExecution(approval, {
        projectId: "project-1",
        taskId: "task-1",
        actionType: "redirect",
        integrationConnectionId: "integration-1",
      }),
    ).toBe(false);

    expect(
      approvalAuthorizesExecution(approval, {
        projectId: "project-1",
        taskId: "task-1",
        actionType: "content_update",
        integrationConnectionId: "integration-2",
      }),
    ).toBe(false);
  });
});
