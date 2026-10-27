import { randomUUID } from "node:crypto";
import { desc, eq } from "drizzle-orm";
import { getDb } from "../../db/client.js";
import { decisions, notes, projects, tasks } from "../../db/schema.js";
import { resolveProjectSlug } from "./slug.js";
import type {
  ProjectDecision,
  ProjectListItem,
  ProjectNote,
  ProjectSnapshot,
  ProjectTask,
  UpsertProjectInput,
} from "./types.js";

function toIso(value: Date): string {
  return value.toISOString();
}

function isUniqueViolation(error: unknown): boolean {
  return Boolean(error && typeof error === "object" && "code" in error && (error as { code?: string }).code === "23505");
}

function mapNote(row: typeof notes.$inferSelect): ProjectNote {
  return {
    id: row.id,
    text: row.text,
    createdAt: toIso(row.createdAt),
  };
}

function mapDecision(row: typeof decisions.$inferSelect): ProjectDecision {
  return {
    id: row.id,
    title: row.title,
    decision: row.decision,
    ...(row.rationale ? { rationale: row.rationale } : {}),
    createdAt: toIso(row.createdAt),
  };
}

function mapTask(row: typeof tasks.$inferSelect): ProjectTask {
  return {
    id: row.id,
    title: row.title,
    status: row.status,
    priority: row.priority,
    ...(row.ownerLabel ? { owner: row.ownerLabel } : {}),
    ...(row.description ? { details: row.description } : {}),
    createdAt: toIso(row.createdAt),
    updatedAt: toIso(row.updatedAt),
  };
}

function mapProjectBase(row: typeof projects.$inferSelect) {
  return {
    id: row.id,
    name: row.name,
    slug: row.slug,
    ...(row.summary ? { description: row.summary } : {}),
    status: row.status,
    goals: row.goals,
    stack: row.stack,
    links: row.links,
    createdAt: toIso(row.createdAt),
    updatedAt: toIso(row.updatedAt),
  };
}

export async function listProjectRows(): Promise<ProjectListItem[]> {
  const db = getDb();
  const [projectRows, noteRows, decisionRows, taskRows] = await Promise.all([
    db.select().from(projects).orderBy(desc(projects.updatedAt)),
    db.select({ projectId: notes.projectId }).from(notes),
    db.select({ projectId: decisions.projectId }).from(decisions),
    db.select({ projectId: tasks.projectId }).from(tasks),
  ]);

  const countByProject = (rows: Array<{ projectId: string }>) => {
    const counts = new Map<string, number>();
    for (const row of rows) counts.set(row.projectId, (counts.get(row.projectId) ?? 0) + 1);
    return counts;
  };

  const noteCounts = countByProject(noteRows);
  const decisionCounts = countByProject(decisionRows);
  const taskCounts = countByProject(taskRows);

  return projectRows.map((row) => ({
    ...mapProjectBase(row),
    noteCount: noteCounts.get(row.id) ?? 0,
    decisionCount: decisionCounts.get(row.id) ?? 0,
    taskCount: taskCounts.get(row.id) ?? 0,
  }));
}

export async function getProjectRow(id: string): Promise<ProjectSnapshot | null> {
  const db = getDb();
  const [project] = await db.select().from(projects).where(eq(projects.id, id)).limit(1);
  if (!project) return null;

  const [projectNotes, projectDecisions, projectTasks] = await Promise.all([
    db.select().from(notes).where(eq(notes.projectId, id)).orderBy(notes.createdAt),
    db.select().from(decisions).where(eq(decisions.projectId, id)).orderBy(decisions.createdAt),
    db.select().from(tasks).where(eq(tasks.projectId, id)).orderBy(tasks.createdAt),
  ]);

  return {
    ...mapProjectBase(project),
    notes: projectNotes.map(mapNote),
    decisions: projectDecisions.map(mapDecision),
    tasks: projectTasks.map(mapTask),
  };
}

export async function upsertProjectRow(input: UpsertProjectInput): Promise<ProjectSnapshot> {
  const db = getDb();
  const id = input.id ?? randomUUID();
  const now = new Date();

  try {
    const [existing] = await db.select().from(projects).where(eq(projects.id, id)).limit(1);
    const slug = resolveProjectSlug(input.slug ?? existing?.slug, input.name, id);

    if (existing) {
      await db
        .update(projects)
        .set({
          name: input.name,
          slug,
          ...(input.description !== undefined ? { summary: input.description } : {}),
          ...(input.goals !== undefined ? { goals: input.goals } : {}),
          ...(input.stack !== undefined ? { stack: input.stack } : {}),
          ...(input.links !== undefined ? { links: input.links } : {}),
          ...(input.status !== undefined ? { status: input.status } : {}),
          updatedAt: now,
        })
        .where(eq(projects.id, id));
    } else {
      await db.insert(projects).values({
        id,
        name: input.name,
        slug,
        summary: input.description,
        status: input.status ?? "active",
        goals: input.goals ?? [],
        stack: input.stack ?? [],
        links: input.links ?? {},
        createdAt: now,
        updatedAt: now,
      });
    }
  } catch (error) {
    if (isUniqueViolation(error)) throw new Error("Project slug already exists");
    throw error;
  }

  const saved = await getProjectRow(id);
  if (!saved) throw new Error("Project could not be read after save");
  return saved;
}
