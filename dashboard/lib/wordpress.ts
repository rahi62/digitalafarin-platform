export type WordPressAuth = { baseUrl: string; username: string; appPassword: string };

export type WordPressPost = {
  id: number;
  date: string;
  modified: string;
  link: string;
  status: string;
  slug: string;
  title: { raw?: string; rendered: string };
  content: { raw?: string; rendered: string };
  excerpt: { raw?: string; rendered: string };
  categories: number[];
};

export type WordPressCategory = { id: number; name: string; slug: string; count: number };

function authorization(input: WordPressAuth) {
  return `Basic ${Buffer.from(`${input.username}:${input.appPassword.replace(/\s+/g, "")}`, "utf8").toString("base64")}`;
}

async function wpRequest<T>(input: WordPressAuth, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(new URL(path, input.baseUrl), {
    ...init,
    headers: {
      Authorization: authorization(input),
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      "User-Agent": "DigitalAfarin-WP-Agent-Dashboard/0.3",
      ...(init.headers ?? {}),
    },
    cache: "no-store",
    signal: AbortSignal.timeout(20_000),
  });
  const data = await response.json().catch(() => null) as (T & { message?: string }) | null;
  if (!response.ok) throw new Error(data?.message || `WordPress returned HTTP ${response.status}`);
  if (data === null) throw new Error("WordPress پاسخ JSON معتبر برنگرداند.");
  return data;
}

export async function checkWordPressConnection(input: WordPressAuth) {
  const data = await wpRequest<{ id?: number; name?: string; roles?: string[] }>(input, "/wp-json/wp/v2/users/me?context=edit");
  return { id: data.id, name: data.name, roles: data.roles ?? [] };
}

export async function listWordPressPosts(input: WordPressAuth, options: { status?: string; search?: string; perPage?: number } = {}) {
  const params = new URLSearchParams({
    context: "edit",
    per_page: String(Math.min(Math.max(options.perPage ?? 20, 1), 50)),
    orderby: "modified",
    order: "desc",
    status: options.status || "any",
  });
  if (options.search?.trim()) params.set("search", options.search.trim());
  return wpRequest<WordPressPost[]>(input, `/wp-json/wp/v2/posts?${params.toString()}`);
}

export async function getWordPressPost(input: WordPressAuth, postId: number) {
  return wpRequest<WordPressPost>(input, `/wp-json/wp/v2/posts/${postId}?context=edit`);
}

export async function listWordPressCategories(input: WordPressAuth) {
  return wpRequest<WordPressCategory[]>(input, "/wp-json/wp/v2/categories?context=edit&per_page=100&orderby=count&order=desc");
}

export async function createWordPressDraft(input: WordPressAuth, draft: { title: string; content: string; excerpt?: string; slug?: string; categoryIds?: number[] }) {
  return wpRequest<WordPressPost>(input, "/wp-json/wp/v2/posts", {
    method: "POST",
    body: JSON.stringify({
      status: "draft",
      title: draft.title,
      content: draft.content,
      excerpt: draft.excerpt || undefined,
      slug: draft.slug || undefined,
      categories: draft.categoryIds?.length ? draft.categoryIds : undefined,
    }),
  });
}

export async function updateWordPressDraft(input: WordPressAuth, postId: number, draft: { title: string; content: string; excerpt?: string; slug?: string; categoryIds?: number[] }) {
  const current = await getWordPressPost(input, postId);
  if (current.status !== "draft") throw new Error("برای حفظ ایمنی، فقط نوشته‌های پیش‌نویس از این پنل قابل ویرایش هستند.");
  return wpRequest<WordPressPost>(input, `/wp-json/wp/v2/posts/${postId}`, {
    method: "POST",
    body: JSON.stringify({
      title: draft.title,
      content: draft.content,
      excerpt: draft.excerpt || "",
      slug: draft.slug || undefined,
      categories: draft.categoryIds ?? [],
    }),
  });
}
