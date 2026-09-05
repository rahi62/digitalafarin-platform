import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { config } from "./config.js";
import { WordPressPageClient, type WpPage } from "./page-client.js";
import { resolveSite, SiteRegistryError } from "./site-registry.js";
import { WordPressError } from "./wordpress.js";

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

function pageSummary(page: WpPage, includeContent = false) {
  return {
    id: page.id,
    title: page.title.raw ?? page.title.rendered ?? "",
    slug: page.slug,
    status: page.status,
    modified: page.modified,
    link: page.link,
    parent: page.parent,
    menuOrder: page.menu_order,
    template: page.template,
    featuredMedia: page.featured_media,
    ...(includeContent ? { content: page.content.raw ?? page.content.rendered ?? "" } : {}),
  };
}

function ensureContentSize(content: string | undefined) {
  if (!content) return;
  const bytes = Buffer.byteLength(content, "utf8");
  if (bytes > config.maxPostContentBytes) throw new Error(`Content exceeds the ${config.maxPostContentBytes}-byte limit`);
}

async function clientFor(siteId: string | undefined, operation: string) {
  const site = await resolveSite(siteId, operation);
  return { site, wp: new WordPressPageClient(site) };
}

const siteIdSchema = z.string().uuid().optional().describe("Registered WordPress site ID. Optional only when exactly one site is enabled.");
const expectedModifiedSchema = z.string().trim().min(10).max(64).optional().describe("Optional modified timestamp returned by wordpress_get_page. If supplied, the write is refused when the page changed since it was read.");
const editablePageFields = {
  title: z.string().trim().min(1).max(500).optional(),
  content: z.string().min(1).optional(),
  slug: z.string().trim().max(200).regex(/^[a-z0-9-]*$/).optional(),
  parent: z.number().int().min(0).optional(),
  menuOrder: z.number().int().min(0).max(1_000_000).optional(),
  template: z.string().trim().max(255).optional(),
};
const seoFields = {
  title: z.string().max(300).optional(),
  description: z.string().max(1000).optional(),
  focusKeyword: z.string().max(500).optional(),
  canonical: z.string().url().max(2048).optional(),
};

export function registerPageTools(server: McpServer) {
  server.registerTool(
    "wordpress_list_pages",
    {
      title: "List WordPress pages",
      description: "Search and list WordPress pages, including drafts and published pages. Makes no changes.",
      inputSchema: {
        siteId: siteIdSchema,
        search: z.string().trim().max(200).optional(),
        status: z.enum(["draft", "pending", "private", "publish", "any"]).default("any"),
        page: z.number().int().min(1).default(1),
        perPage: z.number().int().min(1).max(50).default(20),
      },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, ...input }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_list_pages");
        const pages = await wp.listPages(input);
        return text({ site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, pages: pages.map((page) => pageSummary(page)) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_get_page",
    {
      title: "Read a WordPress page",
      description: "Read one WordPress page by numeric ID, including editable HTML and page attributes. Makes no changes.",
      inputSchema: { siteId: siteIdSchema, id: z.number().int().positive() },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, id }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_get_page");
        return text({ site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, page: pageSummary(await wp.getPage(id), true) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_create_page_draft",
    {
      title: "Create a WordPress page draft",
      description: "Create a new WordPress page strictly as draft. The page can later be completed and explicitly published.",
      inputSchema: {
        siteId: siteIdSchema,
        title: z.string().trim().min(1).max(500),
        content: z.string().min(1),
        slug: z.string().trim().max(200).regex(/^[a-z0-9-]*$/).optional(),
        parent: z.number().int().min(0).optional(),
        menuOrder: z.number().int().min(0).max(1_000_000).optional(),
        template: z.string().trim().max(255).optional(),
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, ...input }) => {
      try {
        ensureContentSize(input.content);
        const { site, wp } = await clientFor(siteId, "wordpress_create_page_draft");
        const page = await wp.createPageDraft(input);
        return text({ created: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, page: pageSummary(page) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_update_page_draft",
    {
      title: "Update a WordPress page draft",
      description: "Update a WordPress page only when it is currently a draft.",
      inputSchema: { siteId: siteIdSchema, id: z.number().int().positive(), ...editablePageFields, expectedModified: expectedModifiedSchema },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, id, expectedModified, ...input }) => {
      try {
        if (Object.values(input).every((value) => value === undefined)) throw new Error("At least one page field must be provided");
        ensureContentSize(input.content);
        const { site, wp } = await clientFor(siteId, "wordpress_update_page_draft");
        const page = await wp.updatePageDraft(id, input, expectedModified);
        return text({ updated: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, page: pageSummary(page) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_publish_page_draft",
    {
      title: "Publish a WordPress page draft",
      description: "Publish an existing page only when it is currently a draft. This makes the page live and must only be used when the user explicitly requests publication.",
      inputSchema: { siteId: siteIdSchema, id: z.number().int().positive(), expectedModified: expectedModifiedSchema },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, id, expectedModified }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_publish_page_draft");
        const page = await wp.publishPageDraft(id, expectedModified);
        return text({ published: true, live: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, page: pageSummary(page) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_update_published_page",
    {
      title: "Update a published WordPress page",
      description: "Edit an existing page only when it is currently published. The page remains published, so changes become live immediately.",
      inputSchema: { siteId: siteIdSchema, id: z.number().int().positive(), ...editablePageFields, expectedModified: expectedModifiedSchema },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, id, expectedModified, ...input }) => {
      try {
        if (Object.values(input).every((value) => value === undefined)) throw new Error("At least one page field must be provided");
        ensureContentSize(input.content);
        const { site, wp } = await clientFor(siteId, "wordpress_update_published_page");
        const page = await wp.updatePublishedPage(id, input, expectedModified);
        return text({ updated: true, live: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, page: pageSummary(page) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_set_page_featured_image",
    {
      title: "Set featured image on a WordPress page",
      description: "Set an existing Media Library image as the featured image of a draft or published page.",
      inputSchema: { siteId: siteIdSchema, pageId: z.number().int().positive(), mediaId: z.number().int().positive(), expectedModified: expectedModifiedSchema },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, pageId, mediaId, expectedModified }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_set_page_featured_image");
        const page = await wp.setPageFeaturedImage(pageId, mediaId, expectedModified);
        return text({ updated: true, live: page.status === "publish", site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, page: pageSummary(page) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_get_page_seo",
    {
      title: "Read SEO metadata for a WordPress page",
      description: "Read available SEO metadata for a WordPress page and report whether controlled SEO writes are supported. Makes no changes.",
      inputSchema: { siteId: siteIdSchema, pageId: z.number().int().positive() },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, pageId }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_get_page_seo");
        return text({ site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, seo: await wp.getPageSeo(pageId) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_update_page_seo",
    {
      title: "Update SEO metadata for a WordPress page",
      description: "Update SEO title, meta description, focus keyword, or canonical URL on a draft or published page through DigitalAfarin Agent Bridge.",
      inputSchema: { siteId: siteIdSchema, pageId: z.number().int().positive(), ...seoFields, expectedModified: expectedModifiedSchema },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, pageId, expectedModified, ...input }) => {
      try {
        if (Object.values(input).every((value) => value === undefined)) throw new Error("At least one SEO field must be provided");
        const { site, wp } = await clientFor(siteId, "wordpress_update_page_seo");
        const seo = await wp.updatePageSeo(pageId, input, expectedModified);
        return text({ updated: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, seo });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_get_page_indexing",
    {
      title: "Read WordPress page indexability override",
      description: "Read whether DigitalAfarin Agent Bridge currently forces noindex for a WordPress page. Makes no changes.",
      inputSchema: { siteId: siteIdSchema, pageId: z.number().int().positive() },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, pageId }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_get_page_indexing");
        return text({ site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, indexing: await wp.getPageIndexing(pageId) });
      } catch (error) { return failure(error); }
    },
  );

  server.registerTool(
    "wordpress_set_page_noindex",
    {
      title: "Set or remove noindex on a WordPress page",
      description: "Set or remove a controlled noindex override on a draft or published page through DigitalAfarin Agent Bridge. Published changes are live immediately.",
      inputSchema: { siteId: siteIdSchema, pageId: z.number().int().positive(), noindex: z.boolean(), expectedModified: expectedModifiedSchema },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, pageId, noindex, expectedModified }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_set_page_noindex");
        const indexing = await wp.setPageNoindex(pageId, noindex, expectedModified);
        return text({ updated: true, live: indexing.status === "publish", site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, indexing });
      } catch (error) { return failure(error); }
    },
  );
}
