import fs from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("Agency proxy trust boundary", () => {
  it("trusts forwarding headers only from the local reverse proxy", async () => {
    const source = await fs.readFile(path.join(process.cwd(), "src/index.ts"), "utf8");
    expect(source).toContain('app.set("trust proxy", "loopback")');
  });
});
