import { describe, expect, it } from "vitest";
import { buildLegacyImportPlan, parseLegacyStore } from "./import-json-store.js";

const projectIdA = "a72e148a-ce73-4d48-bb8a-7824e2677857";
const projectIdB = "b72e148a-ce73-4d48-bb8a-7824e2677858";

function project(id: string, name = "DigitalAfarin") {
  return {
    id,
    name,
    description: "Agency context",
    status: "active" as const,
    goals: ["Grow"],
    stack: ["TypeScript"],
    links: {},
    notes: [
      {
        id: id === projectIdA ? "11111111-1111-4111-8111-111111111111" : "21111111-1111-4111-8111-111111111111",
        text: "Persistent note",
        createdAt: "2026-09-01T10:00:00.000Z",
      },
    ],
    decisions: [
      {
        id: id === projectIdA ? "33333333-3333-4333-8333-333333333333" : "43333333-3333-4333-8333-333333333333",
        title: "Decision",
        decision: "Keep the MCP compatible",
        createdAt: "2026-09-01T11:00:00.000Z",
      },
    ],
    tasks: [
      {
        id: id === projectIdA ? "55555555-5555-4555-8555-555555555555" : "65555555-5555-4555-8555-555555555555",
        title: "Task",
        status: "todo" as const,
        priority: "high" as const,
        owner: "SEO Lead",
        details: "Keep the owner label",
        createdAt: "2026-09-01T12:00:00.000Z",
        updatedAt: "2026-09-01T12:00:00.000Z",
      },
    ],
    createdAt: "2026-09-01T09:00:00.000Z",
    updatedAt: "2026-09-01T12:00:00.000Z",
  };
}

describe("legacy JSON import plan", () => {
  it("preserves IDs, timestamps and nested durable data", () => {
    const store = parseLegacyStore({ projects: [project(projectIdA)] });
    const plan = buildLegacyImportPlan(store);

    expect(plan.projects[0].id).toBe(projectIdA);
    expect(plan.projects[0].createdAt).toBe("2026-09-01T09:00:00.000Z");
    expect(plan.projects[0].notes).toHaveLength(1);
    expect(plan.projects[0].decisions).toHaveLength(1);
    expect(plan.projects[0].tasks[0].owner).toBe("SEO Lead");
    expect(plan.projectSlugs[projectIdA]).toBe("digitalafarin");
  });

  it("derives deterministic unique slugs for duplicate legacy names", () => {
    const store = parseLegacyStore({ projects: [project(projectIdA), project(projectIdB)] });
    const plan = buildLegacyImportPlan(store);

    expect(plan.projectSlugs[projectIdA]).toBe("digitalafarin");
    expect(plan.projectSlugs[projectIdB]).toBe("digitalafarin-b72e148a");
  });

  it("uses a stable fallback when a project name has no ASCII slug characters", () => {
    const store = parseLegacyStore({ projects: [project(projectIdA, "پروژه فارسی")] });
    const plan = buildLegacyImportPlan(store);
    expect(plan.projectSlugs[projectIdA]).toBe("project-a72e148a");
  });
});
