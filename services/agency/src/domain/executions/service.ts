import { eq } from "drizzle-orm";
import { getDb } from "../../db/client.js";
import { approvals, executions, tasks } from "../../db/schema.js";
import { approvalAuthorizesExecution, executionRequiresApproval } from "./policy.js";

export async function queueExecution(input: {
  taskId: string;
  approvalId?: string;
  actionType: string;
  requestPayload: Record<string, unknown>;
}) {
  const db = getDb();
  const [task] = await db.select().from(tasks).where(eq(tasks.id, input.taskId)).limit(1);
  if (!task) throw new Error("Task not found");

  const actionType = input.actionType.trim();
  if (!actionType) throw new Error("Execution action type is required");

  const scope = {
    projectId: task.projectId,
    taskId: task.id,
    actionType,
    integrationConnectionId: task.integrationConnectionId,
  };
  const approvalNeeded = executionRequiresApproval({
    riskLevel: task.riskLevel,
    taskApprovalRequired: task.approvalRequired,
    actionType,
  });

  if (approvalNeeded && !input.approvalId) {
    throw new Error("Approved approval is required before execution");
  }

  if (input.approvalId) {
    const [approval] = await db.select().from(approvals).where(eq(approvals.id, input.approvalId)).limit(1);
    if (!approval || !approvalAuthorizesExecution(approval, scope)) {
      throw new Error("Approval does not authorize this execution scope");
    }
  }

  const [row] = await db
    .insert(executions)
    .values({
      approvalId: input.approvalId,
      taskId: task.id,
      integrationConnectionId: task.integrationConnectionId,
      executorType: task.executorType,
      status: "queued",
      requestPayload: { ...input.requestPayload, actionType },
      retryCount: 0,
    })
    .returning();
  return row;
}

const allowedTransitions = {
  queued: new Set(["running", "cancelled"]),
  running: new Set(["succeeded", "failed", "cancelled"]),
  succeeded: new Set<string>(),
  failed: new Set<string>(),
  cancelled: new Set<string>(),
} as const;

export async function transitionExecution(
  id: string,
  nextStatus: "running" | "succeeded" | "failed" | "cancelled",
  result?: { resultPayload?: Record<string, unknown>; errorMessage?: string },
) {
  const db = getDb();
  const [current] = await db.select().from(executions).where(eq(executions.id, id)).limit(1);
  if (!current) throw new Error("Execution not found");
  if (!allowedTransitions[current.status].has(nextStatus)) {
    throw new Error(`Invalid execution transition: ${current.status} -> ${nextStatus}`);
  }

  const now = new Date();
  const [row] = await db
    .update(executions)
    .set({
      status: nextStatus,
      ...(nextStatus === "running" && !current.startedAt ? { startedAt: now } : {}),
      ...(nextStatus === "succeeded" || nextStatus === "failed" || nextStatus === "cancelled" ? { finishedAt: now } : {}),
      ...(result?.resultPayload !== undefined ? { resultPayload: result.resultPayload } : {}),
      ...(result?.errorMessage !== undefined ? { errorMessage: result.errorMessage } : {}),
    })
    .where(eq(executions.id, id))
    .returning();
  return row;
}
