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
    const category = reasons.find((reason) => reason && /^[A-Za-z_]{3,60}$/.test(reason)) ?? payload?.error?.status ?? "unknown";
    // Google messages sometimes identify a project or API service; omit raw
    // messages from logs and only reveal a small approved diagnostic class.
    const service = (payload?.error?.details ?? []).map((item) => item.metadata?.service).find((value) => value === "searchconsole.googleapis.com");
    const hint = service ? " (service=searchconsole.googleapis.com)" : "";
    throw new Error(`Search Console API HTTP ${response.status} (${category})${hint}`);

  }
  return await response.json() as T;
}
export function propertyUrl(siteUrl: string): string {
  if (!(siteUrl.startsWith("sc-domain:") || siteUrl.startsWith("https://") || siteUrl.startsWith("http://")))
    throw new Error("Invalid GSC property identifier");
  return encodeURIComponent(siteUrl);
}
