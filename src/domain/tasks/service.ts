import { createTaskRow, updateTaskRow } from "./repository.js";
import type { CreateTaskInput, UpdateTaskPatch } from "../projects/types.js";

export function createTaskInPostgres(projectId: string, input: CreateTaskInput) {
  return createTaskRow(projectId, input);
}

export function updateTaskInPostgres(projectId: string, taskId: string, patch: UpdateTaskPatch) {
  return updateTaskRow(projectId, taskId, patch);
}
