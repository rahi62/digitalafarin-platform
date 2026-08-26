import { config } from "./config.js";

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
};

type RequestOptions = {
  method?: "GET" | "POST";
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
};

export class WordPressClient {
  private readonly authorization: string;

  constructor() {
    this.authorization = `Basic ${Buffer.from(
      `${config.wpUsername}:${config.wpAppPassword}`,
      "utf8",
    ).toString("base64")}`;
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const url = new URL(`/wp-json/wp/v2/${path.replace(/^\//, "")}`, config.wpBaseUrl);
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }

    const response = await fetch(url, {
      method: options.method ?? "GET",
      headers: {
        Authorization: this.authorization,
        Accept: "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "DigitalAfarin-WordPress-MCP/0.1",
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: AbortSignal.timeout(20_000),
    });

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

  async updateDraft(
    id: number,
    input: {
      title?: string;
      content?: string;
      excerpt?: string;
      slug?: string;
      categoryIds?: number[];
      tagIds?: number[];
    },
  ) {
    const current = await this.getPost(id);
    if (current.status !== "draft") {
      throw new WordPressError(
        `Refusing to edit post ${id}: expected draft, found ${current.status}`,
        409,
        "not_a_draft",
      );
    }
    return this.request<WpPost>(`posts/${id}`, {
      method: "POST",
      body: { ...input, categories: input.categoryIds, tags: input.tagIds, status: "draft" },
    });
  }

  listCategories(search?: string) {
    return this.request<Array<{ id: number; count: number; name: string; slug: string }>>(
      "categories",
      { query: { search, per_page: 100, orderby: "name", order: "asc" } },
    );
  }
}
