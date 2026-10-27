import { describe, expect, it } from "vitest";
import { resolveWordPressDiscoveryTarget } from "./discovery.js";

describe("WordPress integration discovery target", () => {
  it("resolves only the registered localhost WordPress MCP endpoint", () => {
    expect(
      resolveWordPressDiscoveryTarget({
        type: "wordpress_mcp",
        endpoint: "http://127.0.0.1:3030/mcp",
      }),
    ).toEqual({ endpoint: "http://127.0.0.1:3030/mcp", mode: "read_only" });
  });

  it("rejects non-WordPress and missing endpoints", () => {
    expect(() => resolveWordPressDiscoveryTarget({ type: "github", endpoint: "http://127.0.0.1:3030/mcp" })).toThrow(
      /WordPress MCP/i,
    );
    expect(() => resolveWordPressDiscoveryTarget({ type: "wordpress_mcp", endpoint: null })).toThrow(/endpoint/i);
  });
});
