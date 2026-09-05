const slugPattern = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function isValidProjectSlug(value: string): boolean {
  return slugPattern.test(value);
}

export function normalizeProjectSlug(value: string): string {
  return value
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-{2,}/g, "-");
}

export function deriveProjectSlug(name: string, id: string): string {
  const normalized = normalizeProjectSlug(name);
  return normalized || `project-${id.replace(/-/g, "").slice(0, 8)}`;
}

export function resolveProjectSlug(input: string | undefined, name: string, id: string): string {
  if (!input) return deriveProjectSlug(name, id);
  const normalized = normalizeProjectSlug(input);
  if (!normalized || !isValidProjectSlug(normalized)) {
    throw new Error("Invalid project slug");
  }
  return normalized;
}
