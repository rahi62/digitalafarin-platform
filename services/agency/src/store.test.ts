import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { config } from "./config.js";
import { addNote, createTask, getProject, listProjects, recordDecision, updateTask, upsertProject } from "./store.js";

const originalDataFile = config.dataFile;
const originalStoreDriver = config.storeDriver;
let tempDir = "";

beforeEach(async () => {
  tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "agency-store-"));
  config.dataFile = path.join(tempDir, "agency.json");
  config.storeDriver = "json";
});

afterEach(async () => {
  config.dataFile = originalDataFile;
  config.storeDriver = originalStoreDriver;
  await fs.rm(tempDir, { recursive: true, force: true });
});

describe("legacy JSON compatibility facade", () => {
  it("preserves project, note, decision and task workflows", async () => {
    const projectId = "a72e148a-ce73-4d48-bb8a-7824e2677857";
    await upsertProject({
      id: projectId,
      name: "DigitalAfarin",
      status: "active",
      goals: ["AI-native agency"],
      stack: ["TypeScript"],
    });

    await addNote(projectId, "Persistent context");
    await recordDecision(projectId, "Architecture", "Keep ChatGPT as the reasoning engine");
    const task = await createTask(projectId, { title: "Build Control Center", priority: "high", owner: "Frontend Lead" });
    await updateTask(projectId, task.id, { status: "doing" });

    const project = await getProject(projectId);
    expect(project?.name).toBe("DigitalAfarin");
    expect(project?.notes).toHaveLength(1);
    expect(project?.decisions).toHaveLength(1);
    expect(project?.tasks[0].status).toBe("doing");
    expect(project?.tasks[0].owner).toBe("Frontend Lead");

    const projects = await listProjects();
    expect(projects).toEqual([
      expect.objectContaining({
        id: projectId,
        noteCount: 1,
        decisionCount: 1,
        taskCount: 1,
      }),
    ]);
  });

  it("fails closed and preserves bytes when the JSON store is malformed", async () => {
    const malformed = '{"projects":[';
    await fs.writeFile(config.dataFile, malformed, "utf8");

    await expect(listProjects()).rejects.toThrow();
    expect(await fs.readFile(config.dataFile, "utf8")).toBe(malformed);
  });
});
