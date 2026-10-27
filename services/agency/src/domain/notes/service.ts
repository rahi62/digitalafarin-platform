import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import { getDb } from "../../db/client.js";
import { notes, projects } from "../../db/schema.js";
import type { ProjectNote } from "../projects/types.js";

export async function addNoteInPostgres(projectId: string, text: string): Promise<ProjectNote> {
  const db = getDb();
  const [project] = await db.select({ id: projects.id }).from(projects).where(eq(projects.id, projectId)).limit(1);
  if (!project) throw new Error("Project not found");

  const now = new Date();
  const [row] = await db
    .insert(notes)
    .values({
      id: randomUUID(),
      projectId,
      text,
      createdAt: now,
    })
    .returning();

  await db.update(projects).set({ updatedAt: now }).where(eq(projects.id, projectId));

  return {
    id: row.id,
    text: row.text,
    createdAt: row.createdAt.toISOString(),
  };
}
