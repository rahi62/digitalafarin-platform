import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { config } from "./config.js";
import { addNoteInPostgres } from "./domain/notes/service.js";
import { recordDecisionInPostgres } from "./domain/decisions/service.js";
import {
  getProjectFromPostgres,
  listProjectsFromPostgres,
  upsertProjectInPostgres,
} from "./domain/projects/service.js";
import { createTaskInPostgres, updateTaskInPostgres } from "./domain/tasks/service.js";
import type {
  CreateTaskInput,
  ProjectListItem,
  ProjectSnapshot,
  UpdateTaskPatch,
  UpsertProjectInput,
} from "./domain/projects/types.js";

export type Project = ProjectSnapshot;

type Store = { projects: ProjectSnapshot[] };

let writeQueue: Promise<void> = Promise.resolve();

function withWriteLock<T>(operation: () => Promise<T>): Promise<T> {
  const run = writeQueue.then(operation, operation);
  writeQueue = run.then(() => undefined, () => undefined);
  return run;
}

function isMissingFile(error: unknown): boolean {
  return Boolean(error && typeof error === "object" && "code" in error && (error as NodeJS.ErrnoException).code === "ENOENT");
}

async function ensureJsonStore(): Promise<Store> {
  await fs.mkdir(path.dirname(config.dataFile), { recursive: true });
  try {
    const raw = await fs.readFile(config.dataFile, "utf8");
    return JSON.parse(raw) as Store;
  } catch (error) {
    if (!isMissingFile(error)) throw error;
    const empty: Store = { projects: [] };
    await fs.writeFile(config.dataFile, JSON.stringify(empty, null, 2), { encoding: "utf8", flag: "wx" });
    return empty;
  }
}

async function saveJsonStore(store: Store) {
  const temp = `${config.dataFile}.tmp`;
  await fs.writeFile(temp, JSON.stringify(store, null, 2), "utf8");
  await fs.rename(temp, config.dataFile);
}

async function listProjectsFromJson(): Promise<ProjectListItem[]> {
  const store = await ensureJsonStore();
  return store.projects.map(({ notes, decisions, tasks, ...project }) => ({
    ...project,
    noteCount: notes.length,
    decisionCount: decisions.length,
    taskCount: tasks.length,
  }));
}

async function getProjectFromJson(id: string): Promise<ProjectSnapshot | null> {
  const store = await ensureJsonStore();
  return store.projects.find((project) => project.id === id) ?? null;
}

function upsertProjectInJson(input: UpsertProjectInput): Promise<ProjectSnapshot> {
  return withWriteLock(async () => {
    const store = await ensureJsonStore();
    const now = new Date().toISOString();
    let project = input.id ? store.projects.find((item) => item.id === input.id) : undefined;

    if (!project) {
      project = {
        id: input.id ?? randomUUID(),
        name: input.name,
        ...(input.slug ? { slug: input.slug } : {}),
        ...(input.description !== undefined ? { description: input.description } : {}),
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
      if (input.slug !== undefined) project.slug = input.slug;
      if (input.description !== undefined) project.description = input.description;
      if (input.goals !== undefined) project.goals = input.goals;
      if (input.stack !== undefined) project.stack = input.stack;
      if (input.links !== undefined) project.links = input.links;
      if (input.status !== undefined) project.status = input.status;
      project.updatedAt = now;
    }

    await saveJsonStore(store);
    return project;
  });
}

function addNoteInJson(projectId: string, text: string) {
  return withWriteLock(async () => {
    const store = await ensureJsonStore();
    const project = store.projects.find((item) => item.id === projectId);
    if (!project) throw new Error("Project not found");
    const note = { id: randomUUID(), text, createdAt: new Date().toISOString() };
    project.notes.push(note);
    project.updatedAt = note.createdAt;
    await saveJsonStore(store);
    return note;
  });
}

function recordDecisionInJson(projectId: string, title: string, decision: string, rationale?: string) {
  return withWriteLock(async () => {
    const store = await ensureJsonStore();
    const project = store.projects.find((item) => item.id === projectId);
    if (!project) throw new Error("Project not found");
    const item = {
      id: randomUUID(),
      title,
      decision,
      ...(rationale !== undefined ? { rationale } : {}),
      createdAt: new Date().toISOString(),
    };
    project.decisions.push(item);
    project.updatedAt = item.createdAt;
    await saveJsonStore(store);
    return item;
  });
}

function createTaskInJson(projectId: string, input: CreateTaskInput) {
  return withWriteLock(async () => {
    const store = await ensureJsonStore();
    const project = store.projects.find((item) => item.id === projectId);
    if (!project) throw new Error("Project not found");
    const now = new Date().toISOString();
    const task: ProjectSnapshot["tasks"][number] = {
      id: randomUUID(),
      title: input.title,
      ...(input.details !== undefined ? { details: input.details } : {}),
      priority: input.priority ?? "medium",
      ...(input.owner !== undefined ? { owner: input.owner } : {}),
      status: "todo",
      createdAt: now,
      updatedAt: now,
    };
    project.tasks.push(task);
    project.updatedAt = now;
    await saveJsonStore(store);
    return task;
  });
}

function updateTaskInJson(projectId: string, taskId: string, patch: UpdateTaskPatch) {
  return withWriteLock(async () => {
    const store = await ensureJsonStore();
    const project = store.projects.find((item) => item.id === projectId);
    if (!project) throw new Error("Project not found");
    const task = project.tasks.find((item) => item.id === taskId);
    if (!task) throw new Error("Task not found");

    if (patch.status !== undefined) task.status = patch.status;
    if (patch.priority !== undefined) task.priority = patch.priority;
    if (patch.owner !== undefined) task.owner = patch.owner;
    if (patch.details !== undefined) task.details = patch.details;
    task.updatedAt = new Date().toISOString();
    project.updatedAt = task.updatedAt;
    await saveJsonStore(store);
    return task;
  });
}

export function listProjects() {
  return config.storeDriver === "postgres" ? listProjectsFromPostgres() : listProjectsFromJson();
}

export function getProject(id: string) {
  return config.storeDriver === "postgres" ? getProjectFromPostgres(id) : getProjectFromJson(id);
}

export function upsertProject(input: UpsertProjectInput) {
  return config.storeDriver === "postgres" ? upsertProjectInPostgres(input) : upsertProjectInJson(input);
}

export function addNote(projectId: string, text: string) {
  return config.storeDriver === "postgres" ? addNoteInPostgres(projectId, text) : addNoteInJson(projectId, text);
}

export function recordDecision(projectId: string, title: string, decision: string, rationale?: string) {
  return config.storeDriver === "postgres"
    ? recordDecisionInPostgres(projectId, title, decision, rationale)
    : recordDecisionInJson(projectId, title, decision, rationale);
}

export function createTask(projectId: string, input: CreateTaskInput) {
  return config.storeDriver === "postgres" ? createTaskInPostgres(projectId, input) : createTaskInJson(projectId, input);
}

export function updateTask(projectId: string, taskId: string, patch: UpdateTaskPatch) {
  return config.storeDriver === "postgres"
    ? updateTaskInPostgres(projectId, taskId, patch)
    : updateTaskInJson(projectId, taskId, patch);
}
