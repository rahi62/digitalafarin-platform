import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import { getDb } from "../../db/client.js";
import { decisions, projects } from "../../db/schema.js";
import type { ProjectDecision } from "../projects/types.js";

export async function recordDecisionInPostgres(
  projectId: string,
  title: string,
  decision: string,
  rationale?: string,
): Promise<ProjectDecision> {
  const db = getDb();
  const [project] = await db.select({ id: projects.id }).from(projects).where(eq(projects.id, projectId)).limit(1);
  if (!project) throw new Error("Project not found");

  const now = new Date();
  const [row] = await db
    .insert(decisions)
    .values({
      id: randomUUID(),
      projectId,
      title,
      decision,
      rationale,
      createdAt: now,
    })
    .returning();

  await db.update(projects).set({ updatedAt: now }).where(eq(projects.id, projectId));

  return {
    id: row.id,
    title: row.title,
    decision: row.decision,
    ...(row.rationale ? { rationale: row.rationale } : {}),
    createdAt: row.createdAt.toISOString(),
  };
}
