import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { config } from "./config.js";
import { listSites, resolveSite, SiteRegistryError } from "./site-registry.js";
import { WordPressClient, WordPressError, type WpPost } from "./wordpress.js";

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

function postSummary(post: WpPost, includeContent = false) {
  return {
    id: post.id,
    title: post.title.raw ?? post.title.rendered ?? "",
    slug: post.slug,
    status: post.status,
    modified: post.modified,
    link: post.link,
    excerpt: post.excerpt.raw ?? post.excerpt.rendered ?? "",
    categories: post.categories,
    tags: post.tags,
    ...(includeContent ? { content: post.content.raw ?? post.content.rendered ?? "" } : {}),
  };
}

function ensureContentSize(content: string | undefined) {
  if (!content) return;
  const bytes = Buffer.byteLength(content, "utf8");
  if (bytes > config.maxPostContentBytes) {
    throw new Error(`Content exceeds the ${config.maxPostContentBytes}-byte limit`);
  }
}

async function clientFor(siteId: string | undefined, operation: string) {
  const site = await resolveSite(siteId, operation);
  return { site, wp: new WordPressClient(site) };
}

const siteIdSchema = z.string().uuid().optional().describe(
  "Registered WordPress site ID. Optional only when exactly one site is enabled.",
);

export function createMcpServer() {
  const server = new McpServer({
    name: "DigitalAfarin WordPress Manager",
    version: "0.2.0",
  });

  server.registerTool(
    "wordpress_list_sites",
    {
      title: "List enabled WordPress sites",
      description: "List WordPress sites currently enabled for Agent access. Returns no credentials and makes no changes.",
      inputSchema: {},
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
    },
    async () => {
      try {
        return text({ sites: await listSites() });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_health_check",
    {
      title: "Check WordPress connection",
      description: "Verify an enabled WordPress site and API user. Makes no changes.",
      inputSchema: { siteId: siteIdSchema },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_health_check");
        const user = await wp.getCurrentUser();
        return text({
          ok: true,
          site: { id: site.id, name: site.name, baseUrl: site.baseUrl },
          user: { id: user.id, username: user.username, name: user.name, roles: user.roles },
        });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_search_posts",
    {
      title: "Search WordPress posts",
      description: "Search and list WordPress posts, including drafts, on an enabled site. Makes no changes.",
      inputSchema: {
        siteId: siteIdSchema,
        search: z.string().trim().max(200).optional(),
        status: z.enum(["draft", "pending", "private", "publish", "any"]).default("any"),
        page: z.number().int().min(1).default(1),
        perPage: z.number().int().min(1).max(50).default(10),
      },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, ...input }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_search_posts");
        const posts = await wp.listPosts(input);
        return text({ site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, posts: posts.map((post) => postSummary(post)) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_get_post",
    {
      title: "Read a WordPress post",
      description: "Read one WordPress post by numeric ID, including editable HTML. Makes no changes.",
      inputSchema: { siteId: siteIdSchema, id: z.number().int().positive() },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, id }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_get_post");
        return text({ site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, post: postSummary(await wp.getPost(id), true) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_list_categories",
    {
      title: "List WordPress categories",
      description: "List or search categories and their IDs on an enabled site. Makes no changes.",
      inputSchema: { siteId: siteIdSchema, search: z.string().trim().max(200).optional() },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, search }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_list_categories");
        return text({ site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, categories: await wp.listCategories(search) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_create_draft",
    {
      title: "Create a WordPress draft",
      description: "Create a new post strictly as draft on an enabled site. Never publishes or deletes content.",
      inputSchema: {
        siteId: siteIdSchema,
        title: z.string().trim().min(1).max(500),
        content: z.string().min(1),
        excerpt: z.string().max(5000).optional(),
        slug: z.string().trim().max(200).regex(/^[a-z0-9-]*$/).optional(),
        categoryIds: z.array(z.number().int().positive()).max(20).optional(),
        tagIds: z.array(z.number().int().positive()).max(100).optional(),
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, ...input }) => {
      try {
        ensureContentSize(input.content);
        const { site, wp } = await clientFor(siteId, "wordpress_create_draft");
        const post = await wp.createDraft(input);
        return text({ created: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, post: postSummary(post) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_update_draft",
    {
      title: "Update a WordPress draft",
      description: "Update a post only when its current WordPress status is draft. Refuses published, private, pending, or scheduled posts.",
      inputSchema: {
        siteId: siteIdSchema,
        id: z.number().int().positive(),
        title: z.string().trim().min(1).max(500).optional(),
        content: z.string().min(1).optional(),
        excerpt: z.string().max(5000).optional(),
        slug: z.string().trim().max(200).regex(/^[a-z0-9-]*$/).optional(),
        categoryIds: z.array(z.number().int().positive()).max(20).optional(),
        tagIds: z.array(z.number().int().positive()).max(100).optional(),
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, id, ...input }) => {
      try {
        if (Object.values(input).every((value) => value === undefined)) {
          throw new Error("At least one field must be provided");
        }
        ensureContentSize(input.content);
        const { site, wp } = await clientFor(siteId, "wordpress_update_draft");
        const post = await wp.updateDraft(id, input);
        return text({ updated: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, post: postSummary(post) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  return server;
}
