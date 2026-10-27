import { getProjectRow, listProjectRows, upsertProjectRow } from "./repository.js";
import type { UpsertProjectInput } from "./types.js";

export const listProjectsFromPostgres = listProjectRows;
export const getProjectFromPostgres = getProjectRow;

export function upsertProjectInPostgres(input: UpsertProjectInput) {
  return upsertProjectRow(input);
}
