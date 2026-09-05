import { evaluateApprovalRequirement, type RiskLevel } from "../approvals/policy.js";

export type ExecutionApprovalScope = {
  projectId: string;
  taskId: string;
  actionType: string;
  integrationConnectionId: string | null;
};

export type ApprovalAuthorizationRecord = {
  projectId: string;
  taskId: string | null;
  actionType: string;
  integrationConnectionId: string | null;
  status: string;
};

export function executionRequiresApproval(input: {
  riskLevel: RiskLevel;
  taskApprovalRequired: boolean;
  actionType: string;
}): boolean {
  return evaluateApprovalRequirement({
    riskLevel: input.riskLevel,
    actionType: input.actionType,
    explicitApprovalRequired: input.taskApprovalRequired,
  });
}

export function approvalAuthorizesExecution(
  approval: ApprovalAuthorizationRecord,
  execution: ExecutionApprovalScope,
): boolean {
  return (
    approval.status === "approved" &&
    approval.projectId === execution.projectId &&
    approval.taskId === execution.taskId &&
    approval.actionType === execution.actionType &&
    approval.integrationConnectionId === execution.integrationConnectionId
  );
}
