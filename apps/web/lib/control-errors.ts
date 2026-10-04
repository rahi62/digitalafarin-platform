function safeText(value: unknown): string | null {
  return typeof value === "string" && value.length <= 300 ? value : null;
}

export function describeControlError(status: number, body: Record<string, unknown>): string {
  if (status >= 500) return `Control Plane returned HTTP ${status}`;

  const code = safeText(body.error);
  const message = safeText(body.message) ?? safeText(body.detail)
    ?? (code && /^[a-z_]{1,60}$/.test(code) ? `${code.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase())}.` : null);
  const validation = Object.entries(body)
    .filter(([key]) => !["error", "message", "detail", "blockers"].includes(key))
    .flatMap(([key, value]) => {
      if (!/^[a-z_]{1,40}$/.test(key)) return [];
      const items = Array.isArray(value) ? value : [value];
      return items.map(safeText).filter((item): item is string => item !== null).map((item) => `${key}: ${item}`);
    });

  const blockers = body.blockers && typeof body.blockers === "object" && !Array.isArray(body.blockers)
    ? Object.entries(body.blockers).flatMap(([key, value]) => {
      if (!/^[a-z_]{1,40}$/.test(key) || !Number.isSafeInteger(value) || (value as number) < 1) return [];
      const label = key.replaceAll("_", " ");
      const singular = label.endsWith("ies") ? `${label.slice(0, -3)}y` : label.endsWith("s") ? label.slice(0, -1) : label;
      return `${value} ${value === 1 ? singular : label.endsWith("s") ? label : `${label}s`}`;
    })
    : [];
  const parts = [message, validation.join("; "), blockers.length ? `Blockers: ${blockers.join(", ")}.` : null].filter(Boolean);
  return parts.join(" ") || `Control Plane returned HTTP ${status}`;
}
