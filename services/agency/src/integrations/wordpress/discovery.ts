import { assertLocalWordPressMcpUrl, discoverWordPressMcpTools, type WordPressMcpDiscovery } from "./client.js";

export type WordPressIntegrationRef = {
  type: string;
  endpoint: string | null;
};

export type WordPressDiscoveryTarget = {
  endpoint: string;
  mode: "read_only";
};

export type RegisteredWordPressDiscovery = WordPressMcpDiscovery & {
  mode: "read_only";
};

export function resolveWordPressDiscoveryTarget(connection: WordPressIntegrationRef): WordPressDiscoveryTarget {
  if (connection.type !== "wordpress_mcp") {
    throw new Error("Integration is not a WordPress MCP connection");
  }
  if (!connection.endpoint) {
    throw new Error("WordPress MCP endpoint is not configured");
  }

  const url = assertLocalWordPressMcpUrl(connection.endpoint);
  return { endpoint: url.toString(), mode: "read_only" };
}

export async function discoverRegisteredWordPressTools(connection: WordPressIntegrationRef): Promise<RegisteredWordPressDiscovery> {
  const target = resolveWordPressDiscoveryTarget(connection);
  const discovery = await discoverWordPressMcpTools(target.endpoint);
  return { ...discovery, mode: target.mode };
}
