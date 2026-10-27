import { WordPressError } from "./wordpress.js";

export type WpRendered = { rendered?: string; raw?: string };

export type WpPage = {
  id: number;
  date: string;
  modified: string;
  slug: string;
  status: string;
  link: string;
  title: WpRendered;
  content: WpRendered;
  featured_media: number;
  parent: number;
  menu_order: number;
  template: string;
  yoast_head?: string;
  yoast_head_json?: Record<string, unknown>;
};

export type WpPageIndexing = {
  postId: number;
  status: string;
  noindex: boolean;
  source: string;
};

type RequestOptions = {
  method?: "GET" | "POST" | "DELETE";
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
};

type WordPressConnection = {
  baseUrl: string;
  username: string;
  appPassword: string;
};

export type PageWriteInput = {
  title?: string;
  content?: string;
  slug?: string;
  parent?: number;
  menuOrder?: number;
  template?: string;
};

type SeoInput = {
  title?: string;
  description?: string;
  focusKeyword?: string;
  canonical?: string;
};

export class WordPressPageClient {
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
        "User-Agent": "DigitalAfarin-WordPress-MCP/0.7",
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: AbortSignal.timeout(20_000),
    });
    return this.parseResponse<T>(response);
  }

  private request<T>(path: string, options: RequestOptions = {}) {
    return this.requestRest<T>(`wp/v2/${path.replace(/^\//, "")}`, options);
  }

  private assertUnchanged(current: WpPage, expectedModified?: string) {
    if (expectedModified && current.modified !== expectedModified) {
      throw new WordPressError(
        `Page ${current.id} changed after it was read. Expected modified=${expectedModified}, found ${current.modified}`,
        409,
        "page_changed",
      );
    }
  }

  private pageWriteBody(input: PageWriteInput, status: "draft" | "publish") {
    return {
      title: input.title,
      content: input.content,
      slug: input.slug,
      parent: input.parent,
      menu_order: input.menuOrder,
      template: input.template,
      status,
    };
  }

  listPages(input: { search?: string; page: number; perPage: number; status: string }) {
    return this.request<WpPage[]>("pages", {
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

  getPage(id: number) {
    return this.request<WpPage>(`pages/${id}`, { query: { context: "edit" } });
  }

  createPageDraft(input: Required<Pick<PageWriteInput, "title" | "content">> & PageWriteInput) {
    return this.request<WpPage>("pages", {
      method: "POST",
      body: this.pageWriteBody(input, "draft"),
    });
  }

  async updatePageDraft(id: number, input: PageWriteInput, expectedModified?: string) {
    const current = await this.getPage(id);
    if (current.status !== "draft") {
      throw new WordPressError(
        `Refusing to edit page ${id}: expected draft, found ${current.status}`,
        409,
        "not_a_page_draft",
      );
    }
    this.assertUnchanged(current, expectedModified);
    return this.request<WpPage>(`pages/${id}`, {
      method: "POST",
      body: this.pageWriteBody(input, "draft"),
    });
  }

  async publishPageDraft(id: number, expectedModified?: string) {
    const current = await this.getPage(id);
    if (current.status !== "draft") {
      throw new WordPressError(
        `Refusing to publish page ${id}: expected draft, found ${current.status}`,
        409,
        "not_a_page_draft",
      );
    }
    this.assertUnchanged(current, expectedModified);
    return this.request<WpPage>(`pages/${id}`, { method: "POST", body: { status: "publish" } });
  }

  async updatePublishedPage(id: number, input: PageWriteInput, expectedModified?: string) {
    const current = await this.getPage(id);
    if (current.status !== "publish") {
      throw new WordPressError(
        `Refusing live update for page ${id}: expected publish, found ${current.status}`,
        409,
        "not_published_page",
      );
    }
    this.assertUnchanged(current, expectedModified);
    return this.request<WpPage>(`pages/${id}`, {
      method: "POST",
      body: this.pageWriteBody(input, "publish"),
    });
  }

  async setPageFeaturedImage(pageId: number, mediaId: number, expectedModified?: string) {
    const current = await this.getPage(pageId);
    if (!new Set(["draft", "publish"]).has(current.status)) {
      throw new WordPressError(
        `Refusing to change featured image for page ${pageId}: unsupported status ${current.status}`,
        409,
        "unsupported_page_status",
      );
    }
    this.assertUnchanged(current, expectedModified);
    return this.request<WpPage>(`pages/${pageId}`, {
      method: "POST",
      body: { featured_media: mediaId, status: current.status },
    });
  }

  async getPageSeo(pageId: number) {
    const page = await this.getPage(pageId);
    try {
      const bridge = await this.requestRest<{
        provider: string;
        writable: boolean;
        status?: string;
        fields: { title?: string; description?: string; focusKeyword?: string; canonical?: string };
      }>(`digitalafarin/v1/posts/${pageId}/seo`);
      return { source: "digitalafarin-bridge", ...bridge, page: { id: page.id, status: page.status, link: page.link } };
    } catch (error) {
      if (!(error instanceof WordPressError) || error.status !== 404) throw error;
    }

    if (page.yoast_head_json) {
      return {
        source: "yoast-rest",
        provider: "yoast",
        writable: false,
        fields: page.yoast_head_json,
        page: { id: page.id, status: page.status, link: page.link },
        note: "Yoast REST metadata is read-only. Install DigitalAfarin Agent Bridge for controlled SEO writes.",
      };
    }

    try {
      const rankMath = await this.requestRest<Record<string, unknown>>("rankmath/v1/getHead", { query: { url: page.link } });
      return {
        source: "rankmath-rest",
        provider: "rank-math",
        writable: false,
        fields: rankMath,
        page: { id: page.id, status: page.status, link: page.link },
        note: "Rank Math metadata is read-oriented. Install DigitalAfarin Agent Bridge for controlled SEO writes.",
      };
    } catch (error) {
      if (!(error instanceof WordPressError) || ![400, 404].includes(error.status)) throw error;
    }

    return {
      source: "wordpress",
      provider: "unknown",
      writable: false,
      fields: {},
      page: { id: page.id, status: page.status, link: page.link },
      note: "No supported writable SEO bridge was detected.",
    };
  }

  async updatePageSeo(pageId: number, input: SeoInput, expectedModified?: string) {
    const current = await this.getPage(pageId);
    if (!new Set(["draft", "publish"]).has(current.status)) {
      throw new WordPressError(
        `Refusing to edit SEO metadata for page ${pageId}: unsupported status ${current.status}`,
        409,
        "unsupported_page_status",
      );
    }
    this.assertUnchanged(current, expectedModified);
    try {
      return await this.requestRest<{
        provider: string;
        writable: boolean;
        status?: string;
        fields: { title?: string; description?: string; focusKeyword?: string; canonical?: string };
      }>(`digitalafarin/v1/posts/${pageId}/seo`, { method: "POST", body: input });
    } catch (error) {
      if (error instanceof WordPressError && error.status === 404) {
        throw new WordPressError(
          "DigitalAfarin Agent Bridge is not installed, so page SEO metadata cannot be written safely",
          409,
          "seo_bridge_missing",
        );
      }
      throw error;
    }
  }

  getPageIndexing(pageId: number) {
    return this.requestRest<WpPageIndexing>(`digitalafarin/v1/posts/${pageId}/indexing`);
  }

  async setPageNoindex(pageId: number, noindex: boolean, expectedModified?: string) {
    const current = await this.getPage(pageId);
    if (!new Set(["draft", "publish"]).has(current.status)) {
      throw new WordPressError(
        `Refusing to change indexing for page ${pageId}: unsupported status ${current.status}`,
        409,
        "unsupported_page_status",
      );
    }
    this.assertUnchanged(current, expectedModified);
    return this.requestRest<WpPageIndexing>(`digitalafarin/v1/posts/${pageId}/indexing`, {
      method: "POST",
      body: { noindex },
    });
  }
}
