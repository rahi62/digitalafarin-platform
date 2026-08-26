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
  if (!resolvedHost || !/^[a-z0-9.:[\]-]+$/i.test(resolvedHost)) {
    throw new Error("Public dashboard host could not be resolved safely.");
  }
  if (!new Set(["http", "https"]).has(protocol)) throw new Error("Unsupported public dashboard protocol.");
  return `${protocol}://${resolvedHost}`;
}

export function gscCallbackUrl(origin: string) {
  return new URL("/api/gsc/oauth/callback", `${origin.replace(/\/$/, "")}/`).toString();
}
