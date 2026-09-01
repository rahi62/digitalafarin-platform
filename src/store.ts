import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { config } from "./config.js";

export type Project = {
  id: string;
  name: string;
  description?: string;
  status: "active" | "paused" | "archived";
  goals: string[];
  stack: string[];
  links: Record<string, string>;
  notes: Array<{ id: string; text: string; createdAt: string }>;
  decisions: Array<{ id: string; title: string; decision: string; rationale?: string; createdAt: string }>;
  tasks: Array<{ id: string; title: string; status: "todo" | "doing" | "done" | "blocked"; priority: "low" | "medium" | "high" | "critical"; owner?: string; details?: string; createdAt: string; updatedAt: string }>;
  createdAt: string;
  updatedAt: string;
};

type Store = { projects: Project[] };

let writeQueue: Promise<void> = Promise.resolve();

function withWriteLock<T>(operation: () => Promise<T>): Promise<T> {
  const run = writeQueue.then(operation, operation);
  writeQueue = run.then(() => undefined, () => undefined);
  return run;
}

async function ensureStore(): Promise<Store> {
  await fs.mkdir(path.dirname(config.dataFile), { recursive: true });
  try {
    return JSON.parse(await fs.readFile(config.dataFile, "utf8")) as Store;
  } catch {
    const empty: Store = { projects: [] };
    await fs.writeFile(config.dataFile, JSON.stringify(empty, null, 2), "utf8");
    return empty;
  }
}

async function save(store: Store) {
  const temp = `${config.dataFile}.tmp`;
  await fs.writeFile(temp, JSON.stringify(store, null, 2), "utf8");
  await fs.rename(temp, config.dataFile);
}

export async function listProjects() {
  const store = await ensureStore();
  return store.projects.map(({ notes, decisions, tasks, ...p }) => ({
    ...p,
    noteCount: notes.length,
    decisionCount: decisions.length,
    taskCount: tasks.length,
  }));
}

export async function getProject(id: string) {
  const store = await ensureStore();
  return store.projects.find((p) => p.id === id) ?? null;
}

export function upsertProject(input: { id?: string; name: string; description?: string; goals?: string[]; stack?: string[]; links?: Record<string, string>; status?: Project["status"] }) {
  return withWriteLock(async () => {
    const store = await ensureStore();
    const now = new Date().toISOString();
    let project = input.id ? store.projects.find((p) => p.id === input.id) : undefined;

    if (!project) {
      project = {
        id: input.id ?? randomUUID(),
        name: input.name,
        description: input.description,
        status: input.status ?? "active",
        goals: input.goals ?? [],
        stack: input.stack ?? [],
        links: input.links ?? {},
        notes: [],
        decisions: [],
        tasks: [],
        createdAt: now,
        updatedAt: now,
      };
      store.projects.push(project);
    } else {
      project.name = input.name;
      if (input.description !== undefined) project.description = input.description;
      if (input.goals !== undefined) project.goals = input.goals;
      if (input.stack !== undefined) project.stack = input.stack;
      if (input.links !== undefined) project.links = input.links;
      if (input.status !== undefined) project.status = input.status;
      project.updatedAt = now;
    }

    await save(store);
    return project;
  });
}

export function addNote(projectId: string, text: string) {
  return withWriteLock(async () => {
    const store = await ensureStore();
    const project = store.projects.find((p) => p.id === projectId);
    if (!project) throw new Error("Project not found");
    const note = { id: randomUUID(), text, createdAt: new Date().toISOString() };
    project.notes.push(note);
    project.updatedAt = note.createdAt;
    await save(store);
    return note;
  });
}

export function recordDecision(projectId: string, title: string, decision: string, rationale?: string) {
  return withWriteLock(async () => {
    const store = await ensureStore();
    const project = store.projects.find((p) => p.id === projectId);
    if (!project) throw new Error("Project not found");
    const item = { id: randomUUID(), title, decision, rationale, createdAt: new Date().toISOString() };
    project.decisions.push(item);
    project.updatedAt = item.createdAt;
    await save(store);
    return item;
  });
}

export function createTask(projectId: string, input: { title: string; details?: string; priority?: Project["tasks"][number]["priority"]; owner?: string }) {
  return withWriteLock(async () => {
    const store = await ensureStore();
    const project = store.projects.find((p) => p.id === projectId);
    if (!project) throw new Error("Project not found");
    const now = new Date().toISOString();
    const task: Project["tasks"][number] = {
      id: randomUUID(),
      title: input.title,
      details: input.details,
      priority: input.priority ?? "medium",
      owner: input.owner,
      status: "todo",
      createdAt: now,
      updatedAt: now,
    };
    project.tasks.push(task);
    project.updatedAt = now;
    await save(store);
    return task;
  });
}

export function updateTask(projectId: string, taskId: string, patch: { status?: Project["tasks"][number]["status"]; priority?: Project["tasks"][number]["priority"]; owner?: string; details?: string }) {
  return withWriteLock(async () => {
    const store = await ensureStore();
    const project = store.projects.find((p) => p.id === projectId);
    if (!project) throw new Error("Project not found");
    const task = project.tasks.find((t) => t.id === taskId);
    if (!task) throw new Error("Task not found");
    Object.assign(task, patch, { updatedAt: new Date().toISOString() });
    project.updatedAt = task.updatedAt;
    await save(store);
    return task;
  });
}
