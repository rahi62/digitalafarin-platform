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
  if (!response.ok) throw new Error(`Search Console API HTTP ${response.status}`);
  return await response.json() as T;
}
export function propertyUrl(siteUrl: string): string {
  if (!(siteUrl.startsWith("sc-domain:") || siteUrl.startsWith("https://") || siteUrl.startsWith("http://")))
    throw new Error("Invalid GSC property identifier");
  return encodeURIComponent(siteUrl);
}
