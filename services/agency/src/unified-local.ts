/**
 * Local MCP tool aggregator for Claude Desktop.
 *
 * Deliberately includes ONLY Agency and WordPress/GSC tools. The Platform VPS
 * MCP is excluded: its scopes and production boundaries must stay separate.
 */
import { fileURLToPath } from "node:url";
import path from "node:path";
import { existsSync } from "node:fs";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const platformServices = path.resolve(here, "../../..");
const targets = [
  { id: "agency", script: path.join(platformServices, "agency/dist/local.js") },
  { id: "wordpress", script: path.join(platformServices, "wordpress/dist/local.js") },
];

const upstreams = [];
const registry = new Map();
const server = new Server(
  { name: "DigitalAfarin Local MCP Hub", version: "0.1.0" },
  { capabilities: { tools: { listChanged: false } } },
);
async function close() {
  await Promise.allSettled(upstreams.map(({ client }) => client.close()));
}
try {
  for (const target of targets) {
    if (!existsSync(target.script)) throw new Error(`Missing build: ${target.script}. Build both services first.`);
    const client = new Client({ name: "digitalafarin-hub", version: "0.1.0" });
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [target.script],
      stderr: "inherit",
    });
    await client.connect(transport);
    upstreams.push({ client });
    let cursor;
    do {
      const response = await client.listTools(cursor ? { cursor } : undefined);
      for (const tool of response.tools) {
        if (registry.has(tool.name)) throw new Error(`Duplicate tool name: ${tool.name}`);
        registry.set(tool.name, { client, tool });
      }
      cursor = response.nextCursor;
    } while (cursor);
  }

  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: [...registry.values()].map(({ tool }) => tool),
  }));

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const upstream = registry.get(request.params.name);
    if (!upstream) throw new Error("Unknown or disabled tool");
    return upstream.client.callTool({
      name: request.params.name,
      arguments: request.params.arguments ?? {},
    });
  });

  await server.connect(new StdioServerTransport());
  process.once("SIGINT", () => { void close(); });
  process.once("SIGTERM", () => { void close(); });
} catch (error) {
  console.error("DigitalAfarin local hub failed:", error instanceof Error ? error.message : "unknown error");
  await close();
  process.exitCode = 1;
}
