import { z } from "zod";
import { GscApiError, querySearchAnalytics } from "./gsc.js";
import { GscRegistryError, listGscSites, resolveGscSite } from "./gsc-registry.js";
import { createMcpServer as createWordPressMcpServer } from "./server.js";

function text(value: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }] };
}

function failure(error: unknown) {
  const safe = error instanceof GscApiError
    ? { error: error.message, status: error.status, code: "gsc_api_error" }
    : error instanceof GscRegistryError
      ? { error: error.message, status: error.status, code: "gsc_registry_error" }
      : { error: error instanceof Error ? error.message : "Unexpected error" };
  return { ...text(safe), isError: true };
}

const siteIdSchema = z.string().uuid().optional().describe(
  "WordPress site ID mapped to a Search Console property. Optional only when exactly one GSC-mapped site is enabled.",
);
const dateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Use YYYY-MM-DD");
const dimensionSchema = z.enum(["query", "page", "country", "device", "searchAppearance", "date", "hour"]);
const filterDimensionSchema = z.enum(["query", "page", "country", "device", "searchAppearance"]);
const filterOperatorSchema = z.enum(["contains", "equals", "notContains", "notEquals", "includingRegex", "excludingRegex"]);

export function createMcpServer() {
  const server = createWordPressMcpServer();

  server.registerTool(
    "gsc_list_sites",
    {
      title: "List Search Console mapped sites",
      description: "List enabled WordPress sites that are mapped to a Google Search Console property. Makes no changes.",
      inputSchema: {},
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async () => {
      try {
        return text({ sites: await listGscSites() });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "gsc_search_analytics",
    {
      title: "Query Google Search Console performance",
      description: "Read Search Console performance data for an enabled mapped site. Supports clicks, impressions, CTR, average position, dimensions, filters, search type and pagination. Makes no changes.",
      inputSchema: {
        siteId: siteIdSchema,
        startDate: dateSchema,
        endDate: dateSchema,
        dimensions: z.array(dimensionSchema).max(7).optional(),
        type: z.enum(["web", "image", "video", "news", "discover", "googleNews"]).default("web"),
        filters: z.array(z.object({
          dimension: filterDimensionSchema,
          operator: filterOperatorSchema.default("equals"),
          expression: z.string().min(1).max(4096),
        })).max(20).optional(),
        aggregationType: z.enum(["auto", "byPage", "byProperty"]).default("auto"),
        dataState: z.enum(["final", "all", "hourly_all"]).default("final"),
        rowLimit: z.number().int().min(1).max(25_000).default(1000),
        startRow: z.number().int().min(0).default(0),
      },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, ...input }) => {
      try {
        if (input.startDate > input.endDate) throw new Error("startDate must be before or equal to endDate");
        const resolved = await resolveGscSite(siteId, "gsc_search_analytics");
        const result = await querySearchAnalytics(resolved.accessToken, resolved.site.propertyUrl, input);
        return text({
          site: resolved.site,
          request: {
            startDate: input.startDate,
            endDate: input.endDate,
            dimensions: input.dimensions ?? [],
            type: input.type,
            rowLimit: input.rowLimit,
            startRow: input.startRow,
          },
          rows: result.rows ?? [],
          responseAggregationType: result.responseAggregationType,
          metadata: result.metadata,
          note: "Search Console API returns top rows and does not guarantee every possible row for large result sets.",
        });
      } catch (error) {
        return failure(error);
      }
    },
  );

  return server;
}
