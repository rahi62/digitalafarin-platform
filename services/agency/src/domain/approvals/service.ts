import { and, desc, eq } from "drizzle-orm";
import { getDb } from "../../db/client.js";
import { approvals, projects, tasks } from "../../db/schema.js";
import { evaluateApprovalRequirement, type RiskLevel } from "./policy.js";

const riskRank: Record<RiskLevel, number> = { low: 0, medium: 1, high: 2, critical: 3 };

function maxRisk(left: RiskLevel, right: RiskLevel): RiskLevel {
  return riskRank[left] >= riskRank[right] ? left : right;
}

export async function listApprovals() {
  return getDb().select().from(approvals).orderBy(desc(approvals.requestedAt));
}

export async function getApproval(id: string) {
  const [row] = await getDb().select().from(approvals).where(eq(approvals.id, id)).limit(1);
  return row ?? null;
}

export async function requestApproval(input: {
  projectId: string;
  taskId?: string;
  actionType: string;
  integrationConnectionId?: string;
  riskLevel: RiskLevel;
  requestedBy?: string;
  payload: Record<string, unknown>;
  diffPreview?: Record<string, unknown>;
}) {
  const db = getDb();
  const [project] = await db.select({ id: projects.id }).from(projects).where(eq(projects.id, input.projectId)).limit(1);
  if (!project) throw new Error("Project not found");

  let effectiveRisk = input.riskLevel;
  let explicitApprovalRequired = true;
  if (input.taskId) {
    const [task] = await db.select().from(tasks).where(eq(tasks.id, input.taskId)).limit(1);
    if (!task || task.projectId !== input.projectId) throw new Error("Task not found");
    effectiveRisk = maxRisk(effectiveRisk, task.riskLevel);
    explicitApprovalRequired = task.approvalRequired;
  }

  const required = evaluateApprovalRequirement({
    riskLevel: effectiveRisk,
    actionType: input.actionType,
    explicitApprovalRequired,
  });
  if (!required) throw new Error("Approval is not required by current policy");

  const [row] = await db
    .insert(approvals)
    .values({
      projectId: input.projectId,
      taskId: input.taskId,
      actionType: input.actionType,
      integrationConnectionId: input.integrationConnectionId,
      riskLevel: effectiveRisk,
      requestedBy: input.requestedBy,
      payload: input.payload,
      diffPreview: input.diffPreview,
      status: "pending",
    })
    .returning();
  return row;
}

export async function approve(id: string, userId: string, reason?: string) {
  const db = getDb();
  const [row] = await db
    .update(approvals)
    .set({ status: "approved", reviewedBy: userId, reviewedAt: new Date(), reason })
    .where(and(eq(approvals.id, id), eq(approvals.status, "pending")))
    .returning();
  if (!row) throw new Error("Approval is not pending or does not exist");
  return row;
}

export async function reject(id: string, userId: string, reason: string) {
  const db = getDb();
  const [row] = await db
    .update(approvals)
    .set({ status: "rejected", reviewedBy: userId, reviewedAt: new Date(), reason })
    .where(and(eq(approvals.id, id), eq(approvals.status, "pending")))
    .returning();
  if (!row) throw new Error("Approval is not pending or does not exist");
  return row;
}
