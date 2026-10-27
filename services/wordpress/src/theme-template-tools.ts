import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { resolveSite, SiteRegistryError } from "./site-registry.js";
import { ThemeTemplateClient, ThemeTemplateError } from "./theme-template-client.js";
import { WordPressError } from "./wordpress.js";

function text(value: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }] };
}

function failure(error: unknown) {
  const safe = error instanceof ThemeTemplateError
    ? {
        error: error.message,
        status: error.status,
        code: error.code,
        details: error.details,
        zipFallbackRecommended: Boolean(error.details?.zipFallbackRecommended),
      }
    : error instanceof WordPressError
      ? { error: error.message, status: error.status, code: error.code }
      : error instanceof SiteRegistryError
        ? { error: error.message, status: error.status, code: "site_registry_error" }
        : { error: error instanceof Error ? error.message : "Unexpected error" };
  return { ...text(safe), isError: true };
}

async function clientFor(siteId: string | undefined, operation: string) {
  const site = await resolveSite(siteId, operation);
  return { site, client: new ThemeTemplateClient(site) };
}

const siteIdSchema = z.string().uuid().optional().describe(
  "Registered WordPress site ID. Optional only when exactly one site is enabled.",
);
const pageIdSchema = z.number().int().positive();
const relativePathSchema = z.string().trim().min(1).max(500).describe(
  "Relative PHP path returned by wordpress_resolve_theme_template; never use an absolute filesystem path.",
);
const hashSchema = z.string().regex(/^[a-f0-9]{64}$/i, "Use a 64-character SHA-256 hash");
const replacementSchema = z.string().min(1).max(2_500_000);

function siteSummary(site: { id: string; name: string; baseUrl: string }) {
  return { id: site.id, name: site.name, baseUrl: site.baseUrl };
}

export function registerThemeTemplateTools(server: McpServer) {
  server.registerTool(
    "wordpress_get_active_theme",
    {
      title: "Get active WordPress theme automation status",
      description: "Read the active theme, Theme Automation policy, and host safety capabilities such as PHP lint, atomic rename, backup, and HTTP QA. Makes no changes.",
      inputSchema: { siteId: siteIdSchema },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId }) => {
      try {
        const { site, client } = await clientFor(siteId, "wordpress_get_active_theme");
        return text({ site: siteSummary(site), themeAutomation: await client.getStatus() });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_resolve_theme_template",
    {
      title: "Resolve a pillar Page to its active theme template",
      description: "Resolve a WordPress Page ID or same-site Page URL/path to the actual PHP template currently used by the active theme. Reports sharing/allowlist/write safety without changing files.",
      inputSchema: {
        siteId: siteIdSchema,
        pageId: pageIdSchema.optional(),
        url: z.string().trim().min(1).max(3000).optional(),
      },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, pageId, url }) => {
      try {
        if (!pageId && !url) throw new Error("Provide pageId or url");
        if (pageId && url) throw new Error("Provide pageId or url, not both");
        const { site, client } = await clientFor(siteId, "wordpress_resolve_theme_template");
        return text({ site: siteSummary(site), resolution: await client.resolve({ pageId, url }) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_read_theme_template",
    {
      title: "Read an allowlisted WordPress theme template",
      description: "Read the full PHP source, SHA-256 hash, size and modified time of one allowlisted active-theme template. Makes no changes and never exposes an absolute server path.",
      inputSchema: { siteId: siteIdSchema, relativePath: relativePathSchema },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, relativePath }) => {
      try {
        const { site, client } = await clientFor(siteId, "wordpress_read_theme_template");
        return text({ site: siteSummary(site), file: await client.read(relativePath) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_preview_theme_template_update",
    {
      title: "Preview a WordPress theme template rewrite",
      description: "Validate a proposed full PHP template replacement against the Page-to-template binding, allowlist, stale hash, size and PHP syntax. Returns change summary and proposed hash. It does not change production files.",
      inputSchema: {
        siteId: siteIdSchema,
        pageId: pageIdSchema,
        relativePath: relativePathSchema,
        expectedHash: hashSchema,
        replacementContent: replacementSchema,
      },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, ...input }) => {
      try {
        const { site, client } = await clientFor(siteId, "wordpress_preview_theme_template_update");
        return text({ site: siteSummary(site), preview: await client.preview(input) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_update_theme_template",
    {
      title: "Update a production WordPress pillar template",
      description: "LIVE PRODUCTION CODE CHANGE. Replace an allowlisted active-theme PHP template only after a successful preview. Requires the exact current expectedHash and proposedHash, creates a backup, validates PHP, performs an atomic write, runs HTTP QA, and may auto-rollback on QA failure. Use only when the user explicitly requests the theme/pillar code change.",
      inputSchema: {
        siteId: siteIdSchema,
        pageId: pageIdSchema,
        relativePath: relativePathSchema,
        expectedHash: hashSchema,
        proposedHash: hashSchema,
        replacementContent: replacementSchema,
        qaNeedles: z.array(z.string().min(1).max(500)).max(20).optional(),
      },
      annotations: { readOnlyHint: false, destructiveHint: true, openWorldHint: true },
    },
    async ({ siteId, ...input }) => {
      try {
        const { site, client } = await clientFor(siteId, "wordpress_update_theme_template");
        return text({ site: siteSummary(site), result: await client.update(input) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_list_theme_backups",
    {
      title: "List theme template backups",
      description: "List reversible Theme Automation backup metadata for the active theme. Backup source code is not returned. Makes no changes.",
      inputSchema: {
        siteId: siteIdSchema,
        relativePath: relativePathSchema.optional(),
        limit: z.number().int().min(1).max(100).default(50),
      },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, relativePath, limit }) => {
      try {
        const { site, client } = await clientFor(siteId, "wordpress_list_theme_backups");
        return text({ site: siteSummary(site), ...(await client.listBackups(relativePath, limit)) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_restore_theme_backup",
    {
      title: "Restore a production WordPress theme template backup",
      description: "LIVE PRODUCTION CODE CHANGE. Restore a prior Theme Automation backup after checking the current template hash. The restore creates a safety backup first and remains reversible. Use only when the user explicitly requests rollback/restore.",
      inputSchema: {
        siteId: siteIdSchema,
        backupId: z.string().uuid(),
        expectedCurrentHash: hashSchema,
      },
      annotations: { readOnlyHint: false, destructiveHint: true, openWorldHint: true },
    },
    async ({ siteId, backupId, expectedCurrentHash }) => {
      try {
        const { site, client } = await clientFor(siteId, "wordpress_restore_theme_backup");
        return text({ site: siteSummary(site), result: await client.restoreBackup(backupId, expectedCurrentHash) });
      } catch (error) { return failure(error); }
    },
  );
}
