const PROJECT_SLUG = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/;

export function buildBootstrapOperation(serverId: string, idempotencyKey: string) {
  if (!serverId.trim()) throw new Error("server id is required");
  return {
    server_id: serverId.trim(),
    kind: "server.bootstrap" as const,
    payload: {},
    idempotency_key: idempotencyKey.trim(),
  };
}

export function buildProjectCreate(name: string, slug: string) {
  const cleanName = name.trim();
  const cleanSlug = slug.trim();
  if (!cleanName) throw new Error("project name is required");
  if (!PROJECT_SLUG.test(cleanSlug)) throw new Error("project slug is invalid");
  return { name: cleanName, slug: cleanSlug };
}
