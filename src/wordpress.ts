export class WordPressError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "WordPressError";
  }
}

export type WpRendered = { rendered?: string; raw?: string };

export type WpPost = {
  id: number;
  date: string;
  modified: string;
  slug: string;
  status: string;
  link: string;
  title: WpRendered;
  content: WpRendered;
  excerpt: WpRendered;
  categories: number[];
  tags: number[];
  featured_media: number;
  yoast_head?: string;
  yoast_head_json?: Record<string, unknown>;
};

export type WpMedia = {
  id: number;
  date: string;
  modified: string;
  slug: string;
  status: string;
  link: string;
  title: WpRendered;
  caption: WpRendered;
  description: WpRendered;
  alt_text: string;
  media_type: string;
  mime_type: string;
  source_url: string;
};

export type WpTag = {
  id: number;
  count: number;
  description: string;
  link: string;
  name: string;
  slug: string;
};

type RequestOptions = {
  method?: "GET" | "POST";
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
};

type WordPressConnection = {
  baseUrl: string;
  username: string;
  appPassword: string;
};

type PostWriteInput = {
  title?: string;
  content?: string;
  excerpt?: string;
  slug?: string;
  categoryIds?: number[];
  tagIds?: number[];
};

export class WordPressClient {
  private readonly authorization: string;
  private readonly baseUrl: string;

  constructor(connection: WordPressConnection) {
    this.baseUrl = connection.baseUrl.replace(/\/$/, "");
    this.authorization = `Basic ${Buffer.from(
      `${connection.username}:${connection.appPassword.replace(/\s+/g, "")}`,
      "utf8",
    ).toString("base64")}`;
  }

  private async parseResponse<T>(response: Response): Promise<T> {
    const raw = await response.text();
    let data: unknown;
    try {
      data = raw ? JSON.parse(raw) : null;
    } catch {
      throw new WordPressError("WordPress returned a non-JSON response", response.status);
    }

    if (!response.ok) {
      const error = data as { code?: string; message?: string } | null;
      throw new WordPressError(
        error?.message || `WordPress request failed with HTTP ${response.status}`,
        response.status,
        error?.code,
      );
    }
    return data as T;
  }

  private async requestRest<T>(route: string, options: RequestOptions = {}): Promise<T> {
    const url = new URL(`/wp-json/${route.replace(/^\//, "")}`, this.baseUrl);
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }

    const response = await fetch(url, {
      method: options.method ?? "GET",
      headers: {
        Authorization: this.authorization,
        Accept: "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "DigitalAfarin-WordPress-MCP/0.4",
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: AbortSignal.timeout(20_000),
    });
    return this.parseResponse<T>(response);
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    return this.requestRest<T>(`wp/v2/${path.replace(/^\//, "")}`, options);
  }

  getCurrentUser() {
    return this.request<{
      id: number;
      username: string;
      name: string;
      roles: string[];
      capabilities: Record<string, boolean>;
    }>("users/me", { query: { context: "edit" } });
  }

  listPosts(input: { search?: string; page: number; perPage: number; status: string }) {
    return this.request<WpPost[]>("posts", {
      query: {
        context: "edit",
        search: input.search,
        page: input.page,
        per_page: input.perPage,
        status: input.status,
        orderby: "modified",
        order: "desc",
      },
    });
  }

  getPost(id: number) {
    return this.request<WpPost>(`posts/${id}`, { query: { context: "edit" } });
  }

  createDraft(input: {
    title: string;
    content: string;
    excerpt?: string;
    slug?: string;
    categoryIds?: number[];
    tagIds?: number[];
  }) {
    return this.request<WpPost>("posts", {
      method: "POST",
      body: {
        title: input.title,
        content: input.content,
        excerpt: input.excerpt,
        slug: input.slug,
        categories: input.categoryIds,
        tags: input.tagIds,
        status: "draft",
      },
    });
  }

  private assertUnchanged(current: WpPost, expectedModified?: string) {
    if (expectedModified && current.modified !== expectedModified) {
      throw new WordPressError(
        `Post ${current.id} changed after it was read. Expected modified=${expectedModified}, found ${current.modified}`,
        409,
        "post_changed",
      );
    }
  }

  async updateDraft(id: number, input: PostWriteInput, expectedModified?: string) {
    const current = await this.getPost(id);
    if (current.status !== "draft") {
      throw new WordPressError(
        `Refusing to edit post ${id}: expected draft, found ${current.status}`,
        409,
        "not_a_draft",
      );
    }
    this.assertUnchanged(current, expectedModified);
    return this.request<WpPost>(`posts/${id}`, {
      method: "POST",
      body: { ...input, categories: input.categoryIds, tags: input.tagIds, status: "draft" },
    });
  }

  async publishDraft(id: number, expectedModified?: string) {
    const current = await this.getPost(id);
    if (current.status !== "draft") {
      throw new WordPressError(
        `Refusing to publish post ${id}: expected draft, found ${current.status}`,
        409,
        "not_a_draft",
      );
    }
    this.assertUnchanged(current, expectedModified);
    return this.request<WpPost>(`posts/${id}`, {
      method: "POST",
      body: { status: "publish" },
    });
  }

  async updatePublishedPost(id: number, input: PostWriteInput, expectedModified?: string) {
    const current = await this.getPost(id);
    if (current.status !== "publish") {
      throw new WordPressError(
        `Refusing live update for post ${id}: expected publish, found ${current.status}`,
        409,
        "not_published",
      );
    }
    this.assertUnchanged(current, expectedModified);
    return this.request<WpPost>(`posts/${id}`, {
      method: "POST",
      body: { ...input, categories: input.categoryIds, tags: input.tagIds, status: "publish" },
    });
  }

  listCategories(search?: string) {
    return this.request<Array<{ id: number; count: number; name: string; slug: string }>>(
      "categories",
      { query: { search, per_page: 100, orderby: "name", order: "asc" } },
    );
  }

  listTags(input: { search?: string; page: number; perPage: number }) {
    return this.request<WpTag[]>("tags", {
      query: {
        context: "edit",
        search: input.search,
        page: input.page,
        per_page: input.perPage,
        orderby: "name",
        order: "asc",
      },
    });
  }

  createTag(input: { name: string; slug?: string; description?: string }) {
    return this.request<WpTag>("tags", { method: "POST", body: input });
  }

  listMedia(input: { search?: string; page: number; perPage: number }) {
    return this.request<WpMedia[]>("media", {
      query: {
        context: "edit",
        search: input.search,
        media_type: "image",
        page: input.page,
        per_page: input.perPage,
        orderby: "date",
        order: "desc",
      },
    });
  }

  async uploadMedia(input: { bytes: Buffer; contentType: string; filename: string }) {
    const url = new URL("/wp-json/wp/v2/media", this.baseUrl);
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: this.authorization,
        Accept: "application/json",
        "Content-Type": input.contentType,
        "Content-Disposition": `attachment; filename="${input.filename}"`,
        "User-Agent": "DigitalAfarin-WordPress-MCP/0.4",
      },
      body: new Uint8Array(input.bytes),
      signal: AbortSignal.timeout(30_000),
    });
    return this.parseResponse<WpMedia>(response);
  }

  updateMediaMetadata(
    id: number,
    input: { altText?: string; title?: string; caption?: string; description?: string },
  ) {
    return this.request<WpMedia>(`media/${id}`, {
      method: "POST",
      body: {
        alt_text: input.altText,
        title: input.title,
        caption: input.caption,
        description: input.description,
      },
    });
  }

  async setFeaturedImage(postId: number, mediaId: number, expectedModified?: string) {
    const current = await this.getPost(postId);
    if (!new Set(["draft", "publish"]).has(current.status)) {
      throw new WordPressError(
        `Refusing to change featured image for post ${postId}: unsupported status ${current.status}`,
        409,
        "unsupported_post_status",
      );
    }
    this.assertUnchanged(current, expectedModified);
    return this.request<WpPost>(`posts/${postId}`, {
      method: "POST",
      body: { featured_media: mediaId, status: current.status },
    });
  }

  async getSeo(postId: number) {
    const post = await this.getPost(postId);
    try {
      const bridge = await this.requestRest<{
        provider: string;
        writable: boolean;
        fields: { title?: string; description?: string; focusKeyword?: string; canonical?: string };
      }>(`digitalafarin/v1/posts/${postId}/seo`);
      return { source: "digitalafarin-bridge", ...bridge, post: { id: post.id, status: post.status, link: post.link } };
    } catch (error) {
      if (!(error instanceof WordPressError) || error.status !== 404) throw error;
    }

    if (post.yoast_head_json) {
      return {
        source: "yoast-rest",
        provider: "yoast",
        writable: false,
        fields: post.yoast_head_json,
        post: { id: post.id, status: post.status, link: post.link },
        note: "Yoast REST metadata is read-only. Install the DigitalAfarin Agent Bridge plugin for controlled SEO writes.",
      };
    }

    try {
      const rankMath = await this.requestRest<Record<string, unknown>>("rankmath/v1/getHead", { query: { url: post.link } });
      return {
        source: "rankmath-rest",
        provider: "rank-math",
        writable: false,
        fields: rankMath,
        post: { id: post.id, status: post.status, link: post.link },
        note: "Rank Math headless metadata endpoint is read-oriented. Install the DigitalAfarin Agent Bridge plugin for controlled SEO writes.",
      };
    } catch (error) {
      if (!(error instanceof WordPressError) || ![400, 404].includes(error.status)) throw error;
    }

    return {
      source: "wordpress",
      provider: "unknown",
      writable: false,
      fields: {},
      post: { id: post.id, status: post.status, link: post.link },
      note: "No supported writable SEO bridge was detected.",
    };
  }

  async updateSeo(
    postId: number,
    input: { title?: string; description?: string; focusKeyword?: string; canonical?: string },
    expectedModified?: string,
  ) {
    const current = await this.getPost(postId);
    if (!new Set(["draft", "publish"]).has(current.status)) {
      throw new WordPressError(
        `Refusing to edit SEO metadata for post ${postId}: unsupported status ${current.status}`,
        409,
        "unsupported_post_status",
      );
    }
    this.assertUnchanged(current, expectedModified);
    try {
      return await this.requestRest<{
        provider: string;
        writable: boolean;
        fields: { title?: string; description?: string; focusKeyword?: string; canonical?: string };
      }>(`digitalafarin/v1/posts/${postId}/seo`, { method: "POST", body: input });
    } catch (error) {
      if (error instanceof WordPressError && error.status === 404) {
        throw new WordPressError(
          "DigitalAfarin Agent Bridge is not installed on this WordPress site, so SEO metadata cannot be written safely yet",
          409,
          "seo_bridge_missing",
        );
      }
      throw error;
    }
  }

  async updateDraftSeo(
    postId: number,
    input: { title?: string; description?: string; focusKeyword?: string; canonical?: string },
    expectedModified?: string,
  ) {
    const current = await this.getPost(postId);
    if (current.status !== "draft") {
      throw new WordPressError(
        `Refusing to edit SEO metadata for post ${postId}: expected draft, found ${current.status}`,
        409,
        "not_a_draft",
      );
    }
    return this.updateSeo(postId, input, expectedModified);
  }
}
