import { describe, expect, it } from "vitest";
import { agencyToolNames, createMcpServer } from "./server.js";

describe("DigitalAfarin Agency MCP contract", () => {
  it("keeps the nine established tool names stable", () => {
    expect(agencyToolNames).toEqual([
      "agency_get_team",
      "agency_prepare_council",
      "agency_list_projects",
      "agency_get_project",
      "agency_upsert_project",
      "agency_add_note",
      "agency_record_decision",
      "agency_create_task",
      "agency_update_task",
    ]);
    expect(new Set(agencyToolNames).size).toBe(9);
  });

  it("constructs the MCP server without requiring PostgreSQL while JSON remains the default", () => {
    expect(() => createMcpServer()).not.toThrow();
  });
});
