import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { config } from "./config.js";
import { decodeBase64Image, downloadImage } from "./media.js";
import { listSites, resolveSite, SiteRegistryError } from "./site-registry.js";
import { WordPressClient, WordPressError, type WpMedia, type WpPost, type WpTag } from "./wordpress.js";

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
    featuredMedia: post.featured_media,
    ...(includeContent ? { content: post.content.raw ?? post.content.rendered ?? "" } : {}),
  };
}

function mediaSummary(media: WpMedia) {
  return {
    id: media.id,
    title: media.title.raw ?? media.title.rendered ?? "",
    slug: media.slug,
    altText: media.alt_text,
    caption: media.caption.raw ?? media.caption.rendered ?? "",
    mimeType: media.mime_type,
    sourceUrl: media.source_url,
    link: media.link,
    modified: media.modified,
  };
}

function tagSummary(tag: WpTag) {
  return { id: tag.id, name: tag.name, slug: tag.slug, count: tag.count, description: tag.description };
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
const expectedModifiedSchema = z.string().trim().min(10).max(64).optional().describe(
  "Optional modified timestamp returned by wordpress_get_post. If supplied, the write is refused when the post changed since it was read.",
);
const imageTypeSchema = z.enum(["image/jpeg", "image/png", "image/webp", "image/gif"]);
const maxBase64Chars = Math.ceil(config.maxMediaBytes * 4 / 3) + 200;

const editablePostFields = {
  title: z.string().trim().min(1).max(500).optional(),
  content: z.string().min(1).optional(),
  excerpt: z.string().max(5000).optional(),
  slug: z.string().trim().max(200).regex(/^[a-z0-9-]*$/).optional(),
  categoryIds: z.array(z.number().int().positive()).max(20).optional(),
  tagIds: z.array(z.number().int().positive()).max(100).optional(),
};

const seoFields = {
  title: z.string().max(300).optional(),
  description: z.string().max(1000).optional(),
  focusKeyword: z.string().max(500).optional(),
  canonical: z.string().url().max(2048).optional(),
};

export function createMcpServer() {
  const server = new McpServer({
    name: "DigitalAfarin WordPress Manager",
    version: "0.4.0",
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
    "wordpress_list_tags",
    {
      title: "List WordPress tags",
      description: "List or search WordPress tags and their IDs. Makes no changes.",
      inputSchema: {
        siteId: siteIdSchema,
        search: z.string().trim().max(200).optional(),
        page: z.number().int().min(1).default(1),
        perPage: z.number().int().min(1).max(100).default(50),
      },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, ...input }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_list_tags");
        const tags = await wp.listTags(input);
        return text({ site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, tags: tags.map(tagSummary) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_create_tag",
    {
      title: "Create a WordPress tag",
      description: "Create one non-destructive WordPress tag. Does not modify any post by itself.",
      inputSchema: {
        siteId: siteIdSchema,
        name: z.string().trim().min(1).max(200),
        slug: z.string().trim().max(200).regex(/^[a-z0-9-]*$/).optional(),
        description: z.string().max(2000).optional(),
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, ...input }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_create_tag");
        const tag = await wp.createTag(input);
        return text({ created: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, tag: tagSummary(tag) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_list_media",
    {
      title: "List WordPress images",
      description: "List or search images in the WordPress Media Library. Makes no changes.",
      inputSchema: {
        siteId: siteIdSchema,
        search: z.string().trim().max(200).optional(),
        page: z.number().int().min(1).default(1),
        perPage: z.number().int().min(1).max(50).default(20),
      },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, ...input }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_list_media");
        const media = await wp.listMedia(input);
        return text({ site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, media: media.map(mediaSummary) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_upload_media_from_url",
    {
      title: "Upload image to WordPress from URL",
      description: "Safely download a public HTTPS image and upload it into the enabled site's Media Library. Private/reserved network destinations are blocked.",
      inputSchema: {
        siteId: siteIdSchema,
        sourceUrl: z.string().url().max(3000),
        filename: z.string().trim().min(1).max(180),
        altText: z.string().max(500).optional(),
        title: z.string().max(500).optional(),
        caption: z.string().max(2000).optional(),
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, sourceUrl, filename, altText, title, caption }) => {
      try {
        const image = await downloadImage(sourceUrl, filename, config.maxMediaBytes);
        const { site, wp } = await clientFor(siteId, "wordpress_upload_media_from_url");
        let media = await wp.uploadMedia(image);
        if (altText !== undefined || title !== undefined || caption !== undefined) {
          media = await wp.updateMediaMetadata(media.id, { altText, title, caption });
        }
        return text({ uploaded: true, sourceUrl: image.sourceUrl, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, media: mediaSummary(media) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_upload_media_base64",
    {
      title: "Upload image bytes to WordPress",
      description: "Upload a JPEG, PNG, WebP, or GIF supplied as base64 into the enabled site's Media Library. Useful for generated or locally prepared images.",
      inputSchema: {
        siteId: siteIdSchema,
        data: z.string().min(4).max(maxBase64Chars),
        contentType: imageTypeSchema,
        filename: z.string().trim().min(1).max(180),
        altText: z.string().max(500).optional(),
        title: z.string().max(500).optional(),
        caption: z.string().max(2000).optional(),
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, data, contentType, filename, altText, title, caption }) => {
      try {
        const image = decodeBase64Image({ data, contentType, filename }, config.maxMediaBytes);
        const { site, wp } = await clientFor(siteId, "wordpress_upload_media_base64");
        let media = await wp.uploadMedia(image);
        if (altText !== undefined || title !== undefined || caption !== undefined) {
          media = await wp.updateMediaMetadata(media.id, { altText, title, caption });
        }
        return text({ uploaded: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, media: mediaSummary(media) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_update_media_metadata",
    {
      title: "Update WordPress image metadata",
      description: "Update alt text, title, caption, or description for an existing Media Library image. Does not delete or replace the image.",
      inputSchema: {
        siteId: siteIdSchema,
        mediaId: z.number().int().positive(),
        altText: z.string().max(500).optional(),
        title: z.string().max(500).optional(),
        caption: z.string().max(2000).optional(),
        description: z.string().max(5000).optional(),
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, mediaId, ...input }) => {
      try {
        if (Object.values(input).every((value) => value === undefined)) throw new Error("At least one media metadata field must be provided");
        const { site, wp } = await clientFor(siteId, "wordpress_update_media_metadata");
        const media = await wp.updateMediaMetadata(mediaId, input);
        return text({ updated: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, media: mediaSummary(media) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_set_featured_image",
    {
      title: "Set featured image on a post",
      description: "Set an existing Media Library image as the featured image of a draft or published post. Published posts are changed live; use only when the user requested that change.",
      inputSchema: {
        siteId: siteIdSchema,
        postId: z.number().int().positive(),
        mediaId: z.number().int().positive(),
        expectedModified: expectedModifiedSchema,
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, postId, mediaId, expectedModified }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_set_featured_image");
        const post = await wp.setFeaturedImage(postId, mediaId, expectedModified);
        return text({ updated: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, post: postSummary(post) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_get_seo",
    {
      title: "Read SEO metadata",
      description: "Read available SEO metadata for a post and report whether controlled SEO writes are supported. Makes no changes.",
      inputSchema: { siteId: siteIdSchema, postId: z.number().int().positive() },
      annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, postId }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_get_seo");
        return text({ site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, seo: await wp.getSeo(postId) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_update_draft_seo",
    {
      title: "Update SEO metadata on a draft",
      description: "Update SEO title, meta description, focus keyword, or canonical URL only when the post is a draft.",
      inputSchema: {
        siteId: siteIdSchema,
        postId: z.number().int().positive(),
        ...seoFields,
        expectedModified: expectedModifiedSchema,
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, postId, expectedModified, ...input }) => {
      try {
        if (Object.values(input).every((value) => value === undefined)) throw new Error("At least one SEO field must be provided");
        const { site, wp } = await clientFor(siteId, "wordpress_update_draft_seo");
        const seo = await wp.updateDraftSeo(postId, input, expectedModified);
        return text({ updated: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, seo });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_update_post_seo",
    {
      title: "Update SEO metadata on a draft or published post",
      description: "Update SEO title, meta description, focus keyword, or canonical URL on a draft or published post through DigitalAfarin Agent Bridge. Changes to published posts are live; use only when the user requested a live SEO update.",
      inputSchema: {
        siteId: siteIdSchema,
        postId: z.number().int().positive(),
        ...seoFields,
        expectedModified: expectedModifiedSchema,
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, postId, expectedModified, ...input }) => {
      try {
        if (Object.values(input).every((value) => value === undefined)) throw new Error("At least one SEO field must be provided");
        const { site, wp } = await clientFor(siteId, "wordpress_update_post_seo");
        const seo = await wp.updateSeo(postId, input, expectedModified);
        return text({ updated: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, seo });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_create_draft",
    {
      title: "Create a WordPress draft",
      description: "Create a new post as draft on an enabled site. The draft can later be completed with images and SEO metadata and explicitly published with wordpress_publish_draft.",
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
        ...editablePostFields,
        expectedModified: expectedModifiedSchema,
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, id, expectedModified, ...input }) => {
      try {
        if (Object.values(input).every((value) => value === undefined)) throw new Error("At least one field must be provided");
        ensureContentSize(input.content);
        const { site, wp } = await clientFor(siteId, "wordpress_update_draft");
        const post = await wp.updateDraft(id, input, expectedModified);
        return text({ updated: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, post: postSummary(post) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_publish_draft",
    {
      title: "Publish a WordPress draft",
      description: "Publish an existing post only when it is currently a draft. This makes the post live. Use this tool only when the user explicitly asks to publish.",
      inputSchema: {
        siteId: siteIdSchema,
        id: z.number().int().positive(),
        expectedModified: expectedModifiedSchema,
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, id, expectedModified }) => {
      try {
        const { site, wp } = await clientFor(siteId, "wordpress_publish_draft");
        const post = await wp.publishDraft(id, expectedModified);
        return text({ published: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, post: postSummary(post) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  server.registerTool(
    "wordpress_update_published_post",
    {
      title: "Update a published WordPress post",
      description: "Edit an existing post only when it is currently published. The post remains published, so changes become live immediately. Use only when the user explicitly requests a live content update.",
      inputSchema: {
        siteId: siteIdSchema,
        id: z.number().int().positive(),
        ...editablePostFields,
        expectedModified: expectedModifiedSchema,
      },
      annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: true },
    },
    async ({ siteId, id, expectedModified, ...input }) => {
      try {
        if (Object.values(input).every((value) => value === undefined)) throw new Error("At least one field must be provided");
        ensureContentSize(input.content);
        const { site, wp } = await clientFor(siteId, "wordpress_update_published_post");
        const post = await wp.updatePublishedPost(id, input, expectedModified);
        return text({ updated: true, live: true, site: { id: site.id, name: site.name, baseUrl: site.baseUrl }, post: postSummary(post) });
      } catch (error) {
        return failure(error);
      }
    },
  );

  return server;
}
