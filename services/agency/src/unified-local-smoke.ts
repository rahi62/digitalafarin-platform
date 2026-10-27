import { strict as assert } from "node:assert";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const client = new Client({ name: "digitalafarin-local-smoke", version: "0.1.0" });
const transport = new StdioClientTransport({
  command: process.execPath,
  args: [path.join(here, "unified-local.js")],
  stderr: "inherit",
});

try {
  await client.connect(transport);
  const tools = [];
  let cursor;
  do {
    const page = await client.listTools(cursor ? { cursor } : undefined, { timeout: 15000 });
    tools.push(...page.tools);
    cursor = page.nextCursor;
  } while (cursor);

  const names = tools.map((tool) => tool.name);
  assert.equal(new Set(names).size, names.length, "Duplicate MCP tool names");
  for (const required of ["agency_get_team", "wordpress_list_sites", "gsc_list_sites"]) {
    assert.ok(names.includes(required), `Missing tool: ${required}`);
  }
  assert.ok(!names.some((name) => name.startsWith("vps_")), "VPS tools must not be exposed");
  const response = await client.callTool({ name: "agency_get_team", arguments: {} }, undefined, { timeout: 15000 });
  assert.notEqual(response.isError, true, "Agency read-only smoke tool reported an error");
  assert.ok(Array.isArray(response.content) && response.content.length > 0, "Expected a non-empty tool response");
  console.log(`PASS: unified local MCP discovery (${names.length} tools) and agency_get_team`);
} catch (error) {
  console.error("FAIL: unified local MCP smoke test:", error instanceof Error ? error.message : error);
  process.exitCode = 1;
} finally {
  await client.close();
}
