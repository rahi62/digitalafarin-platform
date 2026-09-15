export function buildDeployRequest(commit?: string) {
  if (!commit) return {};
  if (!/^[0-9a-f]{40}$/.test(commit)) throw new Error("Commit must be an exact SHA-1");
  return { commit };
}

export function projectPath(projectId: string) {
  return `/api/control/v1/projects/${encodeURIComponent(projectId)}/`;
}
