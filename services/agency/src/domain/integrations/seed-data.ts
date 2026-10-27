export const integrationSeedData = [
  {
    slug: "digitalafarin-wordpress-mcp",
    name: "DigitalAfarin WordPress",
    type: "wordpress_mcp" as const,
    endpoint: "http://127.0.0.1:3030/mcp",
    config: {
      healthUrl: "http://127.0.0.1:3030/health",
      mode: "read_only",
    },
  },
] as const;
