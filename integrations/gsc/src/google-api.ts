import { googleFetch } from "./proxy.js";
export const READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly";
export type GscCredentials = { accessToken: string };
export async function googleRead<T>(accessToken: string, endpoint: string, query?: unknown, proxyPort?: number): Promise<T> {
  const url = new URL(endpoint);
  if (url.protocol !== "https:" || !["www.googleapis.com","searchconsole.googleapis.com"].includes(url.hostname))
    throw new Error("Google API endpoint not allowed");
  const response = await googleFetch(url.toString(), {
    method: query === undefined ? "GET" : "POST",
    headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json", ...(query === undefined ? {} : { "Content-Type": "application/json" }) },
    ...(query === undefined ? {} : { body: JSON.stringify(query) }),
    redirect: "error", signal: AbortSignal.timeout(30000)
  }, proxyPort);
  if (!response.ok) {
    // Only expose bounded structural diagnostics. No request Authorization,
    // OAuth tokens, complete response payloads, or free-form Google messages.
    const type = response.headers.get("content-type") ?? "";
    let reason = "unknown";
    let status = "unknown";
    if (type.toLowerCase().includes("json")) {
      const data = await response.json().catch(() => null) as {
        error?: { status?: string; details?: Array<{ reason?: string }>; errors?: Array<{ reason?: string }> };
      } | null;
      const candidate = data?.error?.details?.find((v) => v.reason)?.reason
        ?? data?.error?.errors?.find((v) => v.reason)?.reason;
      if (candidate && /^[A-Za-z_]{3,60}$/.test(candidate)) reason = candidate;
      if (data?.error?.status && /^[A-Z_]{3,60}$/.test(data.error.status)) status = data.error.status;
    } else {
      reason = type.includes("html") ? "non_json_html_response" : "non_json_response";
    }
    throw new Error(`Search Console API HTTP ${response.status} (reason=${reason}, status=${status})`);
  }
  return await response.json() as T;
}
export function propertyUrl(siteUrl: string): string {
  if (!(siteUrl.startsWith("sc-domain:") || siteUrl.startsWith("https://") || siteUrl.startsWith("http://")))
    throw new Error("Invalid GSC property identifier");
  return encodeURIComponent(siteUrl);
}
