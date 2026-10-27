import "dotenv/config";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createMcpServer } from "./server.js";

/**
 * Claude Desktop launches this executable locally.
 * Unlike src/index.ts, it does not start Express or bind to a TCP port.
 * Keep stdout exclusively for MCP protocol data.
 */
const server = createMcpServer();
const transport = new StdioServerTransport();

try {
  await server.connect(transport);
} catch (error) {
  console.error("Agency MCP stdio initialization failed:", error instanceof Error ? error.message : "unknown error");
  process.exitCode = 1;
}
