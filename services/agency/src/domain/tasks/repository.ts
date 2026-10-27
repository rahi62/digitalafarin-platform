import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import { getDb } from "../../db/client.js";
import { projects, tasks } from "../../db/schema.js";
import type { CreateTaskInput, ProjectTask, UpdateTaskPatch } from "../projects/types.js";

function mapTask(row: typeof tasks.$inferSelect): ProjectTask {
  return {
    id: row.id,
    title: row.title,
    status: row.status,
    priority: row.priority,
    ...(row.ownerLabel ? { owner: row.ownerLabel } : {}),
    ...(row.description ? { details: row.description } : {}),
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  };
}

async function ensureProjectExists(projectId: string): Promise<void> {
  const db = getDb();
  const [project] = await db.select({ id: projects.id }).from(projects).where(eq(projects.id, projectId)).limit(1);
  if (!project) throw new Error("Project not found");
}

export async function createTaskRow(projectId: string, input: CreateTaskInput): Promise<ProjectTask> {
  await ensureProjectExists(projectId);
  const db = getDb();
  const now = new Date();
  const id = randomUUID();

  const [row] = await db
    .insert(tasks)
    .values({
      id,
      projectId,
      title: input.title,
      description: input.details,
      priority: input.priority ?? "medium",
      ownerLabel: input.owner,
      status: "todo",
      riskLevel: "low",
      executorType: "manual",
      approvalRequired: false,
      createdAt: now,
      updatedAt: now,
    })
    .returning();

  await db.update(projects).set({ updatedAt: now }).where(eq(projects.id, projectId));
  return mapTask(row);
}

export async function updateTaskRow(projectId: string, taskId: string, patch: UpdateTaskPatch): Promise<ProjectTask> {
  await ensureProjectExists(projectId);
  const db = getDb();
  const [existing] = await db
    .select()
    .from(tasks)
    .where(eq(tasks.id, taskId))
    .limit(1);

  if (!existing || existing.projectId !== projectId) throw new Error("Task not found");

  const now = new Date();
  const [row] = await db
    .update(tasks)
    .set({
      ...(patch.status !== undefined ? { status: patch.status } : {}),
      ...(patch.priority !== undefined ? { priority: patch.priority } : {}),
      ...(patch.owner !== undefined ? { ownerLabel: patch.owner } : {}),
      ...(patch.details !== undefined ? { description: patch.details } : {}),
      ...(patch.status === "done" ? { completedAt: now } : {}),
      ...(patch.status !== undefined && patch.status !== "done" ? { completedAt: null } : {}),
      updatedAt: now,
    })
    .where(eq(tasks.id, taskId))
    .returning();

  await db.update(projects).set({ updatedAt: now }).where(eq(projects.id, projectId));
  return mapTask(row);
}
