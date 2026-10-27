import "dotenv/config";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createMcpServer } from "./server-with-gsc.js";

// Reuse the existing WordPress and GSC registrations, permissions and brokers.
// stdout belongs exclusively to the MCP protocol; diagnostics go to stderr.
const server = createMcpServer();
try {
  await server.connect(new StdioServerTransport());
} catch (error) {
  console.error("WordPress MCP stdio initialization failed:", error instanceof Error ? error.message : "unknown error");
  process.exitCode = 1;
}
