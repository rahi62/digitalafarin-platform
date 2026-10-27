import { randomUUID } from "node:crypto";
import { desc, eq } from "drizzle-orm";
import { getDb } from "../../db/client.js";
import { projects, tasks } from "../../db/schema.js";

export type AdminTaskInput = {
  projectId: string;
  departmentId?: string | null;
  title: string;
  description?: string | null;
  status?: "todo" | "doing" | "done" | "blocked";
  priority?: "low" | "medium" | "high" | "critical";
  riskLevel?: "low" | "medium" | "high" | "critical";
  ownerId?: string | null;
  ownerLabel?: string | null;
  executorType?: "manual" | "wordpress_mcp" | "github" | "automation" | "other";
  integrationConnectionId?: string | null;
  approvalRequired?: boolean;
  expectedImpact?: string | null;
  effort?: string | null;
  dueDate?: string | null;
  createdBy?: string | null;
};

export type AdminTaskPatch = Omit<Partial<AdminTaskInput>, "projectId" | "createdBy">;

function serialize(row: typeof tasks.$inferSelect) {
  return {
    ...row,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
    completedAt: row.completedAt?.toISOString() ?? null,
  };
}

function approvalInvariant(riskLevel: "low" | "medium" | "high" | "critical", requested: boolean | undefined): boolean {
  if (riskLevel === "high" || riskLevel === "critical") return true;
  return requested ?? false;
}

async function ensureProject(projectId: string) {
  const db = getDb();
  const [project] = await db.select({ id: projects.id }).from(projects).where(eq(projects.id, projectId)).limit(1);
  if (!project) throw new Error("Project not found");
}

export async function listAdminTasks() {
  const rows = await getDb().select().from(tasks).orderBy(desc(tasks.updatedAt));
  return rows.map(serialize);
}

export async function getAdminTask(id: string) {
  const [row] = await getDb().select().from(tasks).where(eq(tasks.id, id)).limit(1);
  return row ? serialize(row) : null;
}

export async function createAdminTask(input: AdminTaskInput) {
  await ensureProject(input.projectId);
  const db = getDb();
  const now = new Date();
  const status = input.status ?? "todo";
  const riskLevel = input.riskLevel ?? "low";
  const [row] = await db
    .insert(tasks)
    .values({
      id: randomUUID(),
      projectId: input.projectId,
      departmentId: input.departmentId,
      title: input.title,
      description: input.description,
      status,
      priority: input.priority ?? "medium",
      riskLevel,
      ownerId: input.ownerId,
      ownerLabel: input.ownerLabel,
      executorType: input.executorType ?? "manual",
      integrationConnectionId: input.integrationConnectionId,
      approvalRequired: approvalInvariant(riskLevel, input.approvalRequired),
      expectedImpact: input.expectedImpact,
      effort: input.effort,
      dueDate: input.dueDate,
      createdBy: input.createdBy,
      createdAt: now,
      updatedAt: now,
      completedAt: status === "done" ? now : null,
    })
    .returning();

  await db.update(projects).set({ updatedAt: now }).where(eq(projects.id, input.projectId));
  return serialize(row);
}

export async function updateAdminTask(id: string, patch: AdminTaskPatch) {
  const db = getDb();
  const [existing] = await db.select().from(tasks).where(eq(tasks.id, id)).limit(1);
  if (!existing) return null;

  const now = new Date();
  const status = patch.status ?? existing.status;
  const riskLevel = patch.riskLevel ?? existing.riskLevel;
  const approvalRequired = approvalInvariant(riskLevel, patch.approvalRequired ?? existing.approvalRequired);
  const [row] = await db
    .update(tasks)
    .set({
      ...(patch.departmentId !== undefined ? { departmentId: patch.departmentId } : {}),
      ...(patch.title !== undefined ? { title: patch.title } : {}),
      ...(patch.description !== undefined ? { description: patch.description } : {}),
      ...(patch.status !== undefined ? { status: patch.status } : {}),
      ...(patch.priority !== undefined ? { priority: patch.priority } : {}),
      riskLevel,
      ...(patch.ownerId !== undefined ? { ownerId: patch.ownerId } : {}),
      ...(patch.ownerLabel !== undefined ? { ownerLabel: patch.ownerLabel } : {}),
      ...(patch.executorType !== undefined ? { executorType: patch.executorType } : {}),
      ...(patch.integrationConnectionId !== undefined ? { integrationConnectionId: patch.integrationConnectionId } : {}),
      approvalRequired,
      ...(patch.expectedImpact !== undefined ? { expectedImpact: patch.expectedImpact } : {}),
      ...(patch.effort !== undefined ? { effort: patch.effort } : {}),
      ...(patch.dueDate !== undefined ? { dueDate: patch.dueDate } : {}),
      completedAt: status === "done" ? existing.completedAt ?? now : null,
      updatedAt: now,
    })
    .where(eq(tasks.id, id))
    .returning();

  await db.update(projects).set({ updatedAt: now }).where(eq(projects.id, existing.projectId));
  return serialize(row);
}
