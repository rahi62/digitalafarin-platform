import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

export type WordPressMcpTool = { name: string; description?: string };
export type WordPressMcpDiscovery = {
  endpoint: string;
  tools: WordPressMcpTool[];
  toolCount: number;
};

export function assertLocalWordPressMcpUrl(value: string): URL {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("WordPress MCP endpoint must be a valid localhost URL");
  }

  const localhost = url.hostname === "127.0.0.1" || url.hostname === "localhost" || url.hostname === "[::1]";
  if (url.protocol !== "http:" || !localhost) {
    throw new Error("WordPress MCP endpoint must use HTTP on localhost");
  }
  if (url.port !== "3030") {
    throw new Error("WordPress MCP endpoint must use the dedicated localhost port 3030");
  }
  if (url.pathname !== "/mcp") {
    throw new Error("WordPress MCP endpoint path must be /mcp");
  }
  return url;
}

export async function discoverWordPressMcpTools(endpoint: string): Promise<WordPressMcpDiscovery> {
  const url = assertLocalWordPressMcpUrl(endpoint);
  const client = new Client({ name: "digitalafarin-agency-core", version: "0.2.0" });
  const transport = new StreamableHTTPClientTransport(url);

  try {
    await client.connect(transport);
    const result = await client.listTools();
    const tools = result.tools.map((tool) => ({
      name: tool.name,
      ...(tool.description ? { description: tool.description } : {}),
    }));
    return { endpoint: url.toString(), tools, toolCount: tools.length };
  } finally {
    await client.close().catch(() => undefined);
  }
}
