export const READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly";
export type GscCredentials = { accessToken: string };
export async function googleRead<T>(accessToken: string, endpoint: string, query?: unknown): Promise<T> {
  const url = new URL(endpoint);
  if (url.protocol !== "https:" || !["www.googleapis.com","searchconsole.googleapis.com"].includes(url.hostname))
    throw new Error("Google API endpoint not allowed");
  const response = await fetch(url, {
    method: query === undefined ? "GET" : "POST",
    headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json", ...(query === undefined ? {} : { "Content-Type": "application/json" }) },
    ...(query === undefined ? {} : { body: JSON.stringify(query) }),
    redirect: "error", signal: AbortSignal.timeout(30000)
  });
  if (!response.ok) {
    // Report safe Google error categories without exposing authorization headers,
    // access tokens, account data, or arbitrary upstream error text.
    const payload = await response.json().catch(() => null) as {
      error?: { status?: string; details?: Array<{ reason?: string; metadata?: { service?: string } }>; errors?: Array<{ reason?: string }> };
    } | null;
    const reasons = [...(payload?.error?.details ?? []).map((item) => item.reason), ...(payload?.error?.errors ?? []).map((item) => item.reason)];
    const known = new Set(["SERVICE_DISABLED", "accessNotConfigured", "SERVICE_NOT_ENABLED", "PERMISSION_DENIED", "insufficientPermissions", "forbidden", "rateLimitExceeded", "userRateLimitExceeded"]);
    const category = reasons.find((reason) => reason && known.has(reason)) ?? (payload?.error?.status === "PERMISSION_DENIED" ? "PERMISSION_DENIED" : "unknown");
    throw new Error(`Search Console API HTTP ${response.status} (${category})`);
  }
  return await response.json() as T;
}
export function propertyUrl(siteUrl: string): string {
  if (!(siteUrl.startsWith("sc-domain:") || siteUrl.startsWith("https://") || siteUrl.startsWith("http://")))
    throw new Error("Invalid GSC property identifier");
  return encodeURIComponent(siteUrl);
}
