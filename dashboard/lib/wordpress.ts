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
  tags?: number[];
  featured_media?: number;
};

export type WordPressCategory = { id: number; name: string; slug: string; count: number };
export type WordPressIndexing = { postId: number; status: string; noindex: boolean; source: string };
export type WordPressRedirect = { id: string; source: string; target: string; statusCode: 301; enabled: boolean; createdAt: string; updatedAt: string };

type PostInput = { title: string; content: string; excerpt?: string; slug?: string; categoryIds?: number[] };

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
      "User-Agent": "DigitalAfarin-WP-Agent-Dashboard/0.6",
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
  const data = await wpRequest<{ id?: number; name?: string; roles?: string[]; capabilities?: Record<string, boolean> }>(input, "/wp-json/wp/v2/users/me?context=edit");
  return { id: data.id, name: data.name, roles: data.roles ?? [], capabilities: data.capabilities ?? {} };
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

export async function createWordPressDraft(input: WordPressAuth, draft: PostInput) {
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

async function updateWordPressPost(input: WordPressAuth, postId: number, post: PostInput, requiredStatus: "draft" | "publish") {
  const current = await getWordPressPost(input, postId);
  if (current.status !== requiredStatus) {
    throw new Error(requiredStatus === "draft" ? "این نوشته دیگر Draft نیست؛ صفحه را تازه‌سازی کنید." : "این نوشته دیگر Published نیست؛ صفحه را تازه‌سازی کنید.");
  }
  return wpRequest<WordPressPost>(input, `/wp-json/wp/v2/posts/${postId}`, {
    method: "POST",
    body: JSON.stringify({
      status: requiredStatus,
      title: post.title,
      content: post.content,
      excerpt: post.excerpt || "",
      slug: post.slug || undefined,
      categories: post.categoryIds ?? [],
    }),
  });
}

export function updateWordPressDraft(input: WordPressAuth, postId: number, draft: PostInput) {
  return updateWordPressPost(input, postId, draft, "draft");
}

export function updateWordPressPublishedPost(input: WordPressAuth, postId: number, post: PostInput) {
  return updateWordPressPost(input, postId, post, "publish");
}

export async function publishWordPressDraft(input: WordPressAuth, postId: number) {
  const current = await getWordPressPost(input, postId);
  if (current.status !== "draft") throw new Error("فقط نوشته‌ای که هنوز Draft است قابل انتشار از این عملیات است.");
  return wpRequest<WordPressPost>(input, `/wp-json/wp/v2/posts/${postId}`, {
    method: "POST",
    body: JSON.stringify({ status: "publish" }),
  });
}

export function getWordPressIndexing(input: WordPressAuth, postId: number) {
  return wpRequest<WordPressIndexing>(input, `/wp-json/digitalafarin/v1/posts/${postId}/indexing`);
}

export function setWordPressNoindex(input: WordPressAuth, postId: number, noindex: boolean) {
  return wpRequest<WordPressIndexing>(input, `/wp-json/digitalafarin/v1/posts/${postId}/indexing`, {
    method: "POST",
    body: JSON.stringify({ noindex }),
  });
}

export async function listWordPressRedirects(input: WordPressAuth) {
  const result = await wpRequest<{ redirects: WordPressRedirect[] }>(input, "/wp-json/digitalafarin/v1/redirects");
  return result.redirects;
}

export async function createWordPress301Redirect(input: WordPressAuth, source: string, target: string) {
  const result = await wpRequest<{ redirect: WordPressRedirect }>(input, "/wp-json/digitalafarin/v1/redirects", {
    method: "POST",
    body: JSON.stringify({ source, target }),
  });
  return result.redirect;
}

export function deleteWordPressRedirect(input: WordPressAuth, redirectId: string) {
  return wpRequest<{ deleted: boolean; redirect: WordPressRedirect }>(input, `/wp-json/digitalafarin/v1/redirects/${redirectId}`, { method: "DELETE" });
}

export async function trashWordPressPost(input: WordPressAuth, postId: number) {
  const current = await getWordPressPost(input, postId);
  if (current.status === "trash") throw new Error("این نوشته قبلاً به زباله‌دان منتقل شده است.");
  return wpRequest<WordPressPost>(input, `/wp-json/wp/v2/posts/${postId}?force=false`, { method: "DELETE" });
}

export async function permanentlyDeleteWordPressPost(input: WordPressAuth, postId: number, confirmation: string) {
  const current = await getWordPressPost(input, postId);
  if (current.status !== "trash") throw new Error("حذف دائمی فقط برای نوشته‌ای مجاز است که از قبل داخل Trash باشد.");
  const required = `PERMANENTLY DELETE POST ${postId}`;
  if (confirmation !== required) throw new Error(`عبارت تأیید باید دقیقاً این باشد: ${required}`);
  return wpRequest<{ deleted: boolean; previous: WordPressPost }>(input, `/wp-json/wp/v2/posts/${postId}?force=true`, { method: "DELETE" });
}
