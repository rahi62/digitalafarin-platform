import { describe, expect, it } from "vitest";
import { integrationSeedData } from "./seed-data.js";

describe("Agency integration registry seed", () => {
  it("registers WordPress MCP as a localhost read executor without secrets", () => {
    const wordpress = integrationSeedData.find((item) => item.slug === "digitalafarin-wordpress-mcp");
    expect(wordpress).toEqual({
      slug: "digitalafarin-wordpress-mcp",
      name: "DigitalAfarin WordPress",
      type: "wordpress_mcp",
      endpoint: "http://127.0.0.1:3030/mcp",
      config: { healthUrl: "http://127.0.0.1:3030/health", mode: "read_only" },
    });
    expect(JSON.stringify(wordpress)).not.toMatch(/token|password|secret/i);
  });
});
