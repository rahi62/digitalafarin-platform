import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { discoverWordPressMcpTools } from "../integrations/wordpress/client.js";

const agencyEndpoint = new URL(process.env.AGENCY_MCP_ENDPOINT ?? "http://127.0.0.1:3050/mcp");
const wordpressEndpoint = process.env.WORDPRESS_MCP_ENDPOINT ?? "http://127.0.0.1:3030/mcp";

const requiredAgencyTools = [
  "agency_get_team",
  "agency_prepare_council",
  "agency_list_projects",
  "agency_get_project",
  "agency_upsert_project",
  "agency_add_note",
  "agency_record_decision",
  "agency_create_task",
  "agency_update_task",
] as const;

function assertAgencyLocalEndpoint(url: URL): void {
  const local = url.hostname === "127.0.0.1" || url.hostname === "localhost" || url.hostname === "[::1]";
  if (url.protocol !== "http:" || !local || url.port !== "3050" || url.pathname !== "/mcp") {
    throw new Error("Agency acceptance endpoint must be http://localhost:3050/mcp");
  }
}

async function smokeAgencyMcp() {
  assertAgencyLocalEndpoint(agencyEndpoint);
  const client = new Client({ name: "digitalafarin-agency-acceptance", version: "0.2.0" });
  const transport = new StreamableHTTPClientTransport(agencyEndpoint);

  try {
    await client.connect(transport);
    const listed = await client.listTools();
    const names = new Set(listed.tools.map((tool) => tool.name));
    const missing = requiredAgencyTools.filter((tool) => !names.has(tool));
    if (missing.length) throw new Error(`Agency MCP is missing required tools: ${missing.join(", ")}`);

    const team = await client.callTool({ name: "agency_get_team", arguments: {} });
    if (team.isError) throw new Error("agency_get_team returned an MCP error");

    const projects = await client.callTool({ name: "agency_list_projects", arguments: {} });
    if (projects.isError) throw new Error("agency_list_projects returned an MCP error");

    return { toolCount: listed.tools.length, requiredToolCount: requiredAgencyTools.length };
  } finally {
    await client.close().catch(() => undefined);
  }
}

async function main() {
  const agency = await smokeAgencyMcp();
  const wordpress = await discoverWordPressMcpTools(wordpressEndpoint);
  if (wordpress.toolCount < 1) throw new Error("WordPress MCP returned no tools");

  console.log(
    JSON.stringify(
      {
        ok: true,
        agency,
        wordpress: { toolCount: wordpress.toolCount, endpoint: wordpress.endpoint },
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
