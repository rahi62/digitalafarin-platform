import { describe, expect, it } from "vitest";
import { assertLocalWordPressMcpUrl } from "./client.js";


describe("WordPress MCP client boundary", () => {
  it("accepts the dedicated localhost WordPress MCP endpoint", () => {
    expect(assertLocalWordPressMcpUrl("http://127.0.0.1:3030/mcp").toString()).toBe("http://127.0.0.1:3030/mcp");
    expect(assertLocalWordPressMcpUrl("http://localhost:3030/mcp").port).toBe("3030");
  });

  it("rejects public, TLS and wrong-port endpoints", () => {
    expect(() => assertLocalWordPressMcpUrl("https://wordpress.example.com/mcp")).toThrow(/localhost/i);
    expect(() => assertLocalWordPressMcpUrl("http://127.0.0.1:3050/mcp")).toThrow(/3030/);
    expect(() => assertLocalWordPressMcpUrl("http://127.0.0.1:3030/not-mcp")).toThrow(/\/mcp/);
  });
});
