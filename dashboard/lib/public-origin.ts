function firstHeaderValue(value: string | null) {
  return value?.split(",")[0]?.trim() || "";
}

function isLocalHost(host: string) {
  const normalized = host.toLowerCase();
  return normalized === "localhost" || normalized.startsWith("localhost:") || normalized === "127.0.0.1" || normalized.startsWith("127.0.0.1:") || normalized === "[::1]" || normalized.startsWith("[::1]:");
}

export function resolvePublicOrigin(headers: Headers, fallbackUrl?: string) {
  const forwardedHost = firstHeaderValue(headers.get("x-forwarded-host"));
  const host = forwardedHost || firstHeaderValue(headers.get("host"));
  const fallback = fallbackUrl ? new URL(fallbackUrl) : undefined;
  const resolvedHost = host || fallback?.host;

  if (!resolvedHost || resolvedHost.includes("/") || resolvedHost.includes("\\") || /\s/.test(resolvedHost)) {
    throw new Error("Public dashboard host could not be resolved safely.");
  }

  const forwardedProto = firstHeaderValue(headers.get("x-forwarded-proto"));
  const fallbackProtocol = fallback?.protocol.replace(":", "");
  const protocol = forwardedProto || fallbackProtocol || (isLocalHost(resolvedHost) ? "http" : "https");
  if (!new Set(["http", "https"]).has(protocol)) throw new Error("Unsupported public dashboard protocol.");

  const origin = new URL(`${protocol}://${resolvedHost}`);
  if (origin.username || origin.password) throw new Error("Public dashboard origin is invalid.");
  return origin.origin;
}

export function gscCallbackUrl(origin: string) {
  return new URL("/api/gsc/oauth/callback", `${origin.replace(/\/$/, "")}/`).toString();
}
