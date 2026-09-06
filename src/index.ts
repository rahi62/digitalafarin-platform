import express, { type Request, type Response } from "express";
import { randomUUID, timingSafeEqual } from "node:crypto";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { config } from "./config.js";
import { createMcpServer } from "./server-with-gsc.js";

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: Math.max(1_000_000, Math.ceil(config.maxMediaBytes * 1.5)) }));

function equalsSecret(left: string, right: string) {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

function requestAllowed(req: Request, res: Response): boolean {
  const origin = req.get("origin");
  if (origin && !config.allowedOrigins.has(origin)) {
    res.status(403).json({ error: "Origin not allowed" });
    return false;
  }

  if (config.bearerToken) {
    const supplied = req.get("authorization")?.replace(/^Bearer\s+/i, "") ?? "";
    if (!equalsSecret(supplied, config.bearerToken)) {
      res.status(401).json({ error: "Unauthorized" });
      return false;
    }
  }
  return true;
}

app.get("/health", (_req, res) => {
  res.json({ ok: true, service: "digitalafarin-wordpress-mcp", version: "0.8.0" });
});

app.post("/mcp", async (req, res) => {
  if (!requestAllowed(req, res)) return;

  const server = createMcpServer();
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
  });

  res.on("close", () => {
    void transport.close();
    void server.close();
  });

  try {
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
  } catch (error) {
    console.error(JSON.stringify({ event: "mcp_request_failed", requestId: randomUUID(), error: error instanceof Error ? error.message : "unknown" }));
    if (!res.headersSent) res.status(500).json({ error: "Internal MCP server error" });
  }
});

app.get("/mcp", (req, res) => {
  if (!requestAllowed(req, res)) return;
  res.status(405).set("Allow", "POST").json({ error: "Method not allowed in stateless mode" });
});

app.delete("/mcp", (req, res) => {
  if (!requestAllowed(req, res)) return;
  res.status(405).set("Allow", "POST").json({ error: "Method not allowed in stateless mode" });
});

app.listen(config.port, config.host, () => {
  console.log(`DigitalAfarin WordPress MCP listening on http://${config.host}:${config.port}/mcp`);
});
