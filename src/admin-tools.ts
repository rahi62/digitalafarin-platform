import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { resolveSite, SiteRegistryError } from "./site-registry.js";
import { WordPressClient, WordPressError } from "./wordpress.js";

function text(value: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }] };
}

function failure(error: unknown) {
  const safe = error instanceof WordPressError
    ? { error: error.message, status: error.status, code: error.code }
    : error instanceof SiteRegistryError
      ? { error: error.message, status: error.status, code: "site_registry_error" }
      : { error: error instanceof Error ? error.message : "Unexpected error" };
  return { ...text(safe), isError: true };
}

async function clientFor(siteId: string | undefined, operation: string) {
  const site = await resolveSite(siteId, operation);
  return { site, wp: new WordPressClient(site) };
}

const siteIdSchema = z.string().uuid().optional().describe(
  "Registered WordPress site ID. Optional only when exactly one site is enabled.",
);
const expectedModifiedSchema = z.string().trim().min(10).max(64).optional().describe(
  "Optional modified timestamp returned by wordpress_get_post. The operation is refused when the post changed since it was read.",
);

export function registerAdminTools(server: McpServer) {
  server.registerTool(
    "wordpress_get_indexing",
    {
      title: "Read post indexability override",
      description: "Read whether DigitalAfarin Agent Bridge currently forces noindex for a post. Makes no changes.",
      inputSchema: { siteId: siteIdSchema, postId: z.number().int().positive() },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, postId }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_get_indexing");
        return text({ site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, indexing: await wp.getIndexing(postId) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_set_noindex",
    {
      title: "Set or remove noindex on a post",
      description: "Set or remove a controlled noindex override on a draft or published post through DigitalAfarin Agent Bridge. On published posts this changes live robots output immediately; use only when explicitly requested.",
      inputSchema: {
        siteId: siteIdSchema,
        postId: z.number().int().positive(),
        noindex: z.boolean(),
        expectedModified: expectedModifiedSchema,
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, postId, noindex, expectedModified }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_set_noindex");
        const indexing = await wp.setNoindex(postId, noindex, expectedModified);
        return text({ updated: true, live: indexing.status === "publish", site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, indexing });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_list_redirects",
    {
      title: "List 301 redirects",
      description: "List 301 redirects managed by DigitalAfarin Agent Bridge. Requires an API user with administrator-level manage_options capability. Makes no changes.",
      inputSchema: { siteId: siteIdSchema },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_list_redirects");
        return text({ site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, redirects: await wp.listRedirects() });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_create_301_redirect",
    {
      title: "Create a 301 redirect",
      description: "Create an exact-path permanent 301 redirect managed by DigitalAfarin Agent Bridge. Source must be a relative site path; target may be relative or HTTP(S). This changes live request routing immediately and requires manage_options.",
      inputSchema: {
        siteId: siteIdSchema,
        source: z.string().trim().min(1).max(2048),
        target: z.string().trim().min(1).max(4096),
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, source, target }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_create_301_redirect");
        const redirect = await wp.create301Redirect(source, target);
        return text({ created: true, live: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, redirect });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_delete_redirect",
    {
      title: "Delete a managed 301 redirect",
      description: "Delete one 301 redirect previously created by DigitalAfarin Agent Bridge. This changes live routing immediately and requires manage_options.",
      inputSchema: { siteId: siteIdSchema, redirectId: z.string().uuid() },
      annotations: { readOnlyHint: false, destructiveHint: true, openWorldHint: true },
    },
    async ({ siteId, redirectId }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_delete_redirect");
        const result = await wp.deleteRedirect(redirectId);
        return text({ ...result, live: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl } });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_trash_post",
    {
      title: "Move a WordPress post to trash",
      description: "Move a post to WordPress Trash using the native REST API. This is reversible in WordPress but removes the post from normal public availability. Use only when the user explicitly asks to delete/trash the post.",
      inputSchema: {
        siteId: siteIdSchema,
        id: z.number().int().positive(),
        expectedModified: expectedModifiedSchema,
      },
      annotations: { readOnlyHint: false, destructiveHint: true, openWorldHint: true },
    },
    async ({ siteId, id, expectedModified }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_trash_post");
        const post = await wp.trashPost(id, expectedModified);
        return text({ trashed: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, post: { id: post.id, status: post.status, slug: post.slug, modified: post.modified } });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_delete_post_permanently",
    {
      title: "Permanently delete a trashed WordPress post",
      description: "Permanently delete a post only when it is already in WordPress Trash. This cannot be undone. confirmation must exactly equal `PERMANENTLY DELETE POST <id>`. Use only after explicit user authorization for permanent deletion.",
      inputSchema: {
        siteId: siteIdSchema,
        id: z.number().int().positive(),
        confirmation: z.string().trim().min(1).max(100),
        expectedModified: expectedModifiedSchema,
      },
      annotations: { readOnlyHint: false, destructiveHint: true, openWorldHint: true },
    },
    async ({ siteId, id, confirmation, expectedModified }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_delete_post_permanently");
        const result = await wp.permanentlyDeletePost(id, confirmation, expectedModified);
        return text({ permanentlyDeleted: result.deleted, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, previous: { id: result.previous.id, status: result.previous.status, slug: result.previous.slug } });
      } catch (error) {
        return failure(error);
      }
    },
  );
}
