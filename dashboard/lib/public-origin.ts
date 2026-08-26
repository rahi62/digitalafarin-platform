function firstHeaderValue(value: string | null) {
  return value?.split(",")[0]?.trim() || "";
}

export function resolvePublicOrigin(headers: Headers, fallbackUrl?: string) {
  const forwardedHost = firstHeaderValue(headers.get("x-forwarded-host"));
  const host = forwardedHost || firstHeaderValue(headers.get("host"));
  const forwardedProto = firstHeaderValue(headers.get("x-forwarded-proto"));
  const fallback = fallbackUrl ? new URL(fallbackUrl) : undefined;
  const protocol = forwardedProto || fallback?.protocol.replace(":", "") || "https";
  const resolvedHost = host || fallback?.host;

  if (!resolvedHost || resolvedHost.includes("/") || resolvedHost.includes("\\") || /\s/.test(resolvedHost)) {
    throw new Error("Public dashboard host could not be resolved safely.");
  }
  if (!new Set(["http", "https"]).has(protocol)) throw new Error("Unsupported public dashboard protocol.");

  const origin = new URL(`${protocol}://${resolvedHost}`);
  if (origin.username || origin.password) throw new Error("Public dashboard origin is invalid.");
  return origin.origin;
}

export function gscCallbackUrl(origin: string) {
  return new URL("/api/gsc/oauth/callback", `${origin.replace(/\/$/, "")}/`).toString();
}
