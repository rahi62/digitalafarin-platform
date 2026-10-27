import "dotenv/config";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const base = (process.env.COOLIFY_URL ?? "").trim().replace(/\/+$/, "");
const token = (process.env.COOLIFY_TOKEN ?? "").trim();
if (!base || !token) {
  console.error("Coolify MCP: set COOLIFY_URL and COOLIFY_TOKEN in the local process environment");
  process.exit(1);
}
let url: URL;
try { url = new URL(base); } catch { throw new Error("Invalid COOLIFY_URL"); }
if (url.protocol !== "https:" && !(url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname))) {
  throw new Error("COOLIFY_URL requires HTTPS except for localhost");
}
if (url.username || url.password || url.search || url.hash || url.pathname !== "/") {
  throw new Error("COOLIFY_URL must be an origin without credentials, query, or path");
}

async function read(endpoint: string): Promise<unknown> {
  const response = await fetch(new URL(`/api/v1/${endpoint}`, url), {
    method: "GET",
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    signal: AbortSignal.timeout(12000),
    redirect: "error",
  });
  if (!response.ok) throw new Error(`Coolify API returned HTTP ${response.status}`);
  return response.json();
}
const server = new McpServer({ name: "DigitalAfarin Coolify Readonly", version: "0.1.0" });
function register(name: string, title: string, endpoint: string) {
  server.registerTool(name, {
    title,
    description: `Read ${title.toLowerCase()} from Coolify; makes no changes and does not expose credentials.`,
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
  }, async () => {
    try {
      const value = await read(endpoint);
      return { content: [{ type: "text" as const, text: JSON.stringify(value) }] };
    } catch (error) {
      return { content: [{ type: "text" as const, text: error instanceof Error ? error.message : "Coolify request failed" }], isError: true };
    }
  });
}
register("coolify_list_servers", "Coolify servers", "servers");
register("coolify_list_applications", "Coolify applications", "applications");
register("coolify_list_projects", "Coolify projects", "projects");

try {
  await server.connect(new StdioServerTransport());
} catch (error) {
  console.error("Coolify MCP failed:", error instanceof Error ? error.message : "unknown error");
  process.exitCode = 1;
}
