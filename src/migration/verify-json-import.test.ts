import { describe, expect, it } from "vitest";
import { compareImportedRecords, type ImportedRecordSnapshot } from "./verify-json-import.js";

const source: ImportedRecordSnapshot = {
  projects: [{ id: "00000000-0000-4000-8000-000000000001", createdAt: "2026-09-01T10:00:00.000Z", updatedAt: "2026-09-02T10:00:00.000Z" }],
  notes: [{ id: "00000000-0000-4000-8000-000000000002", createdAt: "2026-09-01T11:00:00.000Z" }],
  decisions: [{ id: "00000000-0000-4000-8000-000000000003", createdAt: "2026-09-01T12:00:00.000Z" }],
  tasks: [{ id: "00000000-0000-4000-8000-000000000004", createdAt: "2026-09-01T13:00:00.000Z", updatedAt: "2026-09-02T13:00:00.000Z" }],
};

describe("JSON import verification", () => {
  it("passes when every legacy id and timestamp is preserved", () => {
    expect(compareImportedRecords(source, structuredClone(source))).toEqual({ ok: true, errors: [] });
  });

  it("reports missing records and timestamp drift", () => {
    const actual = structuredClone(source);
    actual.notes = [];
    actual.tasks[0]!.updatedAt = "2026-09-03T13:00:00.000Z";

    const result = compareImportedRecords(source, actual);
    expect(result.ok).toBe(false);
    expect(result.errors).toContain("notes: missing 00000000-0000-4000-8000-000000000002");
    expect(result.errors).toContain("tasks: updatedAt mismatch for 00000000-0000-4000-8000-000000000004");
  });
});
