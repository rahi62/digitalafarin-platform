import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import { getDb, closeDb } from "../db/client.js";
import { decisions, notes, projects, tasks } from "../db/schema.js";
import { deriveProjectSlug } from "../domain/projects/slug.js";

const noteSchema = z.object({
  id: z.string().uuid(),
  text: z.string(),
  createdAt: z.string().datetime(),
});

const decisionSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  decision: z.string(),
  rationale: z.string().optional(),
  createdAt: z.string().datetime(),
});

const taskSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  status: z.enum(["todo", "doing", "done", "blocked"]),
  priority: z.enum(["low", "medium", "high", "critical"]),
  owner: z.string().optional(),
  details: z.string().optional(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

const projectSchema = z.object({
  id: z.string().uuid(),
  name: z.string().min(1),
  slug: z.string().optional(),
  description: z.string().optional(),
  status: z.enum(["active", "paused", "archived"]),
  goals: z.array(z.string()),
  stack: z.array(z.string()),
  links: z.record(z.string(), z.string()),
  notes: z.array(noteSchema),
  decisions: z.array(decisionSchema),
  tasks: z.array(taskSchema),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

const legacyStoreSchema = z.object({ projects: z.array(projectSchema) });
export type LegacyStore = z.infer<typeof legacyStoreSchema>;

export type ImportReport = {
  projects: number;
  notes: number;
  decisions: number;
  tasks: number;
};

export type LegacyImportPlan = LegacyStore & {
  projectSlugs: Record<string, string>;
};

export function parseLegacyStore(value: unknown): LegacyStore {
  return legacyStoreSchema.parse(value);
}

export function buildLegacyImportPlan(store: LegacyStore): LegacyImportPlan {
  const used = new Set<string>();
  const projectSlugs: Record<string, string> = {};

  for (const project of store.projects) {
    const requested = project.slug?.trim();
    const base = requested || deriveProjectSlug(project.name, project.id);
    let slug = base;
    if (used.has(slug)) slug = `${base}-${project.id.replace(/-/g, "").slice(0, 8)}`;
    used.add(slug);
    projectSlugs[project.id] = slug;
  }

  return { ...store, projectSlugs };
}

export async function importJsonStore(sourcePath: string): Promise<ImportReport> {
  const raw = await fs.readFile(sourcePath, "utf8");
  const plan = buildLegacyImportPlan(parseLegacyStore(JSON.parse(raw)));
  const db = getDb();
  const report: ImportReport = { projects: 0, notes: 0, decisions: 0, tasks: 0 };

  await db.transaction(async (tx) => {
    for (const project of plan.projects) {
      const createdAt = new Date(project.createdAt);
      const updatedAt = new Date(project.updatedAt);
      const slug = plan.projectSlugs[project.id];

      await tx
        .insert(projects)
        .values({
          id: project.id,
          name: project.name,
          slug,
          type: "internal",
          status: project.status,
          health: "healthy",
          priority: "medium",
          summary: project.description,
          goals: project.goals,
          stack: project.stack,
          links: project.links,
          createdAt,
          updatedAt,
        })
        .onConflictDoUpdate({
          target: projects.id,
          set: {
            name: project.name,
            slug,
            status: project.status,
            summary: project.description,
            goals: project.goals,
            stack: project.stack,
            links: project.links,
            createdAt,
            updatedAt,
          },
        });
      report.projects += 1;

      for (const note of project.notes) {
        await tx
          .insert(notes)
          .values({
            id: note.id,
            projectId: project.id,
            text: note.text,
            createdAt: new Date(note.createdAt),
          })
          .onConflictDoUpdate({
            target: notes.id,
            set: {
              projectId: project.id,
              text: note.text,
              createdAt: new Date(note.createdAt),
            },
          });
        report.notes += 1;
      }

      for (const item of project.decisions) {
        await tx
          .insert(decisions)
          .values({
            id: item.id,
            projectId: project.id,
            title: item.title,
            decision: item.decision,
            rationale: item.rationale,
            createdAt: new Date(item.createdAt),
          })
          .onConflictDoUpdate({
            target: decisions.id,
            set: {
              projectId: project.id,
              title: item.title,
              decision: item.decision,
              rationale: item.rationale,
              createdAt: new Date(item.createdAt),
            },
          });
        report.decisions += 1;
      }

      for (const task of project.tasks) {
        await tx
          .insert(tasks)
          .values({
            id: task.id,
            projectId: project.id,
            title: task.title,
            description: task.details,
            status: task.status,
            priority: task.priority,
            riskLevel: "low",
            ownerLabel: task.owner,
            executorType: "manual",
            approvalRequired: false,
            createdAt: new Date(task.createdAt),
            updatedAt: new Date(task.updatedAt),
            completedAt: task.status === "done" ? new Date(task.updatedAt) : null,
          })
          .onConflictDoUpdate({
            target: tasks.id,
            set: {
              projectId: project.id,
              title: task.title,
              description: task.details,
              status: task.status,
              priority: task.priority,
              ownerLabel: task.owner,
              updatedAt: new Date(task.updatedAt),
              completedAt: task.status === "done" ? new Date(task.updatedAt) : null,
            },
          });
        report.tasks += 1;
      }
    }
  });

  return report;
}

async function runFromCli() {
  const sourcePath = process.argv[2];
  if (!sourcePath) throw new Error("Usage: tsx src/migration/import-json-store.ts <path-to-store.json>");
  const report = await importJsonStore(sourcePath);
  console.log(JSON.stringify(report, null, 2));
}

const isCli = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isCli) {
  runFromCli()
    .catch((error) => {
      console.error(error instanceof Error ? error.message : error);
      process.exitCode = 1;
    })
    .finally(async () => {
      await closeDb();
    });
}
