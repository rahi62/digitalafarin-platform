import fs from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";

const root = process.cwd();
const migrationPath = path.join(root, "drizzle", "0000_agency_core.sql");
const journalPath = path.join(root, "drizzle", "meta", "_journal.json");

describe("database migration baseline", () => {
  it("ships a committed Drizzle migration journal and initial SQL", async () => {
    const [sql, journalRaw] = await Promise.all([
      fs.readFile(migrationPath, "utf8"),
      fs.readFile(journalPath, "utf8"),
    ]);
    const journal = JSON.parse(journalRaw) as { entries?: Array<{ tag?: string }> };

    expect(journal.entries?.some((entry) => entry.tag === "0000_agency_core")).toBe(true);
    for (const table of [
      "projects",
      "tasks",
      "approvals",
      "executions",
      "users",
      "sessions",
      "departments",
      "workflows",
      "integration_connections",
      "activity_logs",
    ]) {
      expect(sql).toContain(`CREATE TABLE \"${table}\"`);
    }
    expect(sql).toContain('CREATE TYPE "public"."risk_level"');
    expect(sql).toContain('CREATE UNIQUE INDEX "projects_slug_unique"');
  });
});
