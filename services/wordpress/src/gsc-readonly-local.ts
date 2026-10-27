import "dotenv/config";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

/** Local-only Google Search Console reader. No WordPress broker or storage. */
const clientId = process.env.GSC_CLIENT_ID?.trim();
const clientSecret = process.env.GSC_CLIENT_SECRET?.trim();
const refreshToken = process.env.GSC_REFRESH_TOKEN?.trim();
if (!clientId || !clientSecret || !refreshToken) {
  console.error("GSC read-only MCP: GSC_CLIENT_ID, GSC_CLIENT_SECRET, GSC_REFRESH_TOKEN required");
  process.exit(1);
}
let cached: { token: string; expiresAt: number } | undefined;
async function accessToken(): Promise<string> {
  if (cached && Date.now() < cached.expiresAt - 60_000) return cached.token;
  const response = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: clientId!, client_secret: clientSecret!, refresh_token: refreshToken!, grant_type: "refresh_token" }),
    signal: AbortSignal.timeout(15_000),
    redirect: "error",
  });
  if (!response.ok) throw new Error(`GSC OAuth refresh failed (HTTP ${response.status})`);
  const data = await response.json() as { access_token?: string; expires_in?: number };
  if (!data.access_token) throw new Error("GSC OAuth response missing access token");
  cached = { token: data.access_token, expiresAt: Date.now() + (data.expires_in ?? 3600) * 1000 };
  return data.access_token;
}
async function google<T>(endpoint: string, body?: unknown): Promise<T> {
  const response = await fetch(endpoint, {
    method: body === undefined ? "GET" : "POST",
    headers: { authorization: `Bearer ${await accessToken()}`, accept: "application/json", ...(body === undefined ? {} : { "content-type": "application/json" }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    signal: AbortSignal.timeout(30_000),
    redirect: "error",
  });
  if (!response.ok) throw new Error(`Google Search Console returned HTTP ${response.status}`);
  return await response.json() as T;
}
function success(data: unknown) { return { content: [{ type: "text" as const, text: JSON.stringify(data) }] }; }
function failure(error: unknown) { return { content: [{ type: "text" as const, text: error instanceof Error ? error.message : "GSC request failed" }], isError: true }; }
const server = new McpServer({ name: "DigitalAfarin GSC Readonly", version: "0.1.0" });
const annotation = { readOnlyHint: true, destructiveHint: false, openWorldHint: true };
server.registerTool("gsc_list_properties", {
  title: "List Search Console properties",
  description: "List properties granted to the connected Google user; only read access.",
  inputSchema: {}, annotations: annotation,
}, async () => {
  try {
    const result = await google<{ siteEntry?: Array<{ siteUrl: string; permissionLevel: string }> }>("https://www.googleapis.com/webmasters/v3/sites");
    return success({ properties: result.siteEntry ?? [] });
  } catch (error) { return failure(error); }
});
server.registerTool("gsc_read_performance", {
  title: "Read Search Console search performance",
  description: "Return raw clicks, impressions, CTR and average position. Claude handles comparisons and analysis.",
  inputSchema: {
    property: z.string().min(3).max(2048),
    startDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    endDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    dimensions: z.array(z.enum(["query", "page", "country", "device", "date", "searchAppearance"])).max(6).optional(),
    rowLimit: z.number().int().min(1).max(25000).default(1000),
    startRow: z.number().int().min(0).default(0),
    filters: z.array(z.object({
      dimension: z.enum(["query", "page", "country", "device", "searchAppearance"]),
      operator: z.enum(["equals", "contains", "notEquals", "notContains", "includingRegex", "excludingRegex"]).default("equals"),
      expression: z.string().min(1).max(4096),
    })).max(20).optional(),
  }, annotations: annotation,
}, async ({ property, startDate, endDate, dimensions, rowLimit, startRow, filters }) => {
  try {
    if (startDate > endDate) throw new Error("startDate must be on or before endDate");
    const body = {
      startDate, endDate, dimensions, rowLimit, startRow, type: "web", dataState: "final",
      ...(filters?.length ? { dimensionFilterGroups: [{ groupType: "and", filters }] } : {}),
    };
    const result = await google<Record<string, unknown>>(
      `https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(property)}/searchAnalytics/query`, body,
    );
    return success({ property, startDate, endDate, ...result, note: "GSC returns top rows, not a guaranteed complete export." });
  } catch (error) { return failure(error); }
});
try {
  await server.connect(new StdioServerTransport());
} catch (error) {
  console.error("GSC read-only MCP startup failed:", error instanceof Error ? error.message : "unknown error");
  process.exitCode = 1;
}
