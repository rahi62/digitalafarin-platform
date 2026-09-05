import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { closeDb, getDb } from "../db/client.js";
import { decisions, notes, projects, tasks } from "../db/schema.js";
import { parseLegacyStore, type LegacyStore } from "./import-json-store.js";

type CreatedRecord = { id: string; createdAt: string };
type UpdatedRecord = CreatedRecord & { updatedAt: string };

export type ImportedRecordSnapshot = {
  projects: UpdatedRecord[];
  notes: CreatedRecord[];
  decisions: CreatedRecord[];
  tasks: UpdatedRecord[];
};

export type ImportVerificationResult = { ok: boolean; errors: string[] };

function normalizeIso(value: string | Date): string {
  return (value instanceof Date ? value : new Date(value)).toISOString();
}

function compareGroup(
  label: keyof ImportedRecordSnapshot,
  expected: CreatedRecord[],
  actual: CreatedRecord[],
  compareUpdatedAt: boolean,
): string[] {
  const errors: string[] = [];
  const actualById = new Map(actual.map((item) => [item.id, item]));

  for (const source of expected) {
    const target = actualById.get(source.id);
    if (!target) {
      errors.push(`${label}: missing ${source.id}`);
      continue;
    }
    if (normalizeIso(source.createdAt) !== normalizeIso(target.createdAt)) {
      errors.push(`${label}: createdAt mismatch for ${source.id}`);
    }
    if (compareUpdatedAt) {
      const sourceUpdated = (source as UpdatedRecord).updatedAt;
      const targetUpdated = (target as UpdatedRecord).updatedAt;
      if (normalizeIso(sourceUpdated) !== normalizeIso(targetUpdated)) {
        errors.push(`${label}: updatedAt mismatch for ${source.id}`);
      }
    }
  }

  return errors;
}

export function compareImportedRecords(
  expected: ImportedRecordSnapshot,
  actual: ImportedRecordSnapshot,
): ImportVerificationResult {
  const errors = [
    ...compareGroup("projects", expected.projects, actual.projects, true),
    ...compareGroup("notes", expected.notes, actual.notes, false),
    ...compareGroup("decisions", expected.decisions, actual.decisions, false),
    ...compareGroup("tasks", expected.tasks, actual.tasks, true),
  ];
  return { ok: errors.length === 0, errors };
}

export function snapshotLegacyStore(store: LegacyStore): ImportedRecordSnapshot {
  return {
    projects: store.projects.map((project) => ({
      id: project.id,
      createdAt: normalizeIso(project.createdAt),
      updatedAt: normalizeIso(project.updatedAt),
    })),
    notes: store.projects.flatMap((project) =>
      project.notes.map((note) => ({ id: note.id, createdAt: normalizeIso(note.createdAt) })),
    ),
    decisions: store.projects.flatMap((project) =>
      project.decisions.map((decision) => ({ id: decision.id, createdAt: normalizeIso(decision.createdAt) })),
    ),
    tasks: store.projects.flatMap((project) =>
      project.tasks.map((task) => ({
        id: task.id,
        createdAt: normalizeIso(task.createdAt),
        updatedAt: normalizeIso(task.updatedAt),
      })),
    ),
  };
}

export async function readDatabaseImportSnapshot(): Promise<ImportedRecordSnapshot> {
  const db = getDb();
  const [projectRows, noteRows, decisionRows, taskRows] = await Promise.all([
    db.select({ id: projects.id, createdAt: projects.createdAt, updatedAt: projects.updatedAt }).from(projects),
    db.select({ id: notes.id, createdAt: notes.createdAt }).from(notes),
    db.select({ id: decisions.id, createdAt: decisions.createdAt }).from(decisions),
    db.select({ id: tasks.id, createdAt: tasks.createdAt, updatedAt: tasks.updatedAt }).from(tasks),
  ]);

  return {
    projects: projectRows.map((row) => ({ id: row.id, createdAt: row.createdAt.toISOString(), updatedAt: row.updatedAt.toISOString() })),
    notes: noteRows.map((row) => ({ id: row.id, createdAt: row.createdAt.toISOString() })),
    decisions: decisionRows.map((row) => ({ id: row.id, createdAt: row.createdAt.toISOString() })),
    tasks: taskRows.map((row) => ({ id: row.id, createdAt: row.createdAt.toISOString(), updatedAt: row.updatedAt.toISOString() })),
  };
}

export async function verifyJsonImport(sourcePath: string): Promise<ImportVerificationResult> {
  const raw = await fs.readFile(sourcePath, "utf8");
  const legacy = parseLegacyStore(JSON.parse(raw));
  return compareImportedRecords(snapshotLegacyStore(legacy), await readDatabaseImportSnapshot());
}

async function runFromCli() {
  const sourcePath = process.argv[2];
  if (!sourcePath) throw new Error("Usage: tsx src/migration/verify-json-import.ts <path-to-store.json>");
  const result = await verifyJsonImport(sourcePath);
  console.log(JSON.stringify(result, null, 2));
  if (!result.ok) process.exitCode = 2;
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
