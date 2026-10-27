import type { WordPressAuth } from "./wordpress";

export type WordPressPage = {
  id: number;
  date: string;
  modified: string;
  link: string;
  status: string;
  slug: string;
  title: { raw?: string; rendered: string };
  content: { raw?: string; rendered: string };
  featured_media?: number;
  parent: number;
  menu_order: number;
  template: string;
};

export type DashboardPageInput = {
  title: string;
  content: string;
  slug?: string;
  parent?: number;
  menuOrder?: number;
  template?: string;
};

function authorization(input: WordPressAuth) {
  return `Basic ${Buffer.from(`${input.username}:${input.appPassword.replace(/\s+/g, "")}`, "utf8").toString("base64")}`;
}

async function wpPageRequest<T>(input: WordPressAuth, path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(new URL(path, input.baseUrl), {
    ...init,
    headers: {
      Authorization: authorization(input),
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      "User-Agent": "DigitalAfarin-WP-Agent-Dashboard/0.7",
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

function writeBody(page: DashboardPageInput, status: "draft" | "publish") {
  return {
    status,
    title: page.title,
    content: page.content,
    slug: page.slug || undefined,
    parent: page.parent ?? 0,
    menu_order: page.menuOrder ?? 0,
    template: page.template || undefined,
  };
}

export async function listWordPressPages(input: WordPressAuth, options: { status?: string; search?: string; perPage?: number } = {}) {
  const params = new URLSearchParams({
    context: "edit",
    per_page: String(Math.min(Math.max(options.perPage ?? 20, 1), 50)),
    orderby: "modified",
    order: "desc",
    status: options.status || "any",
  });
  if (options.search?.trim()) params.set("search", options.search.trim());
  return wpPageRequest<WordPressPage[]>(input, `/wp-json/wp/v2/pages?${params.toString()}`);
}

export function getWordPressPage(input: WordPressAuth, pageId: number) {
  return wpPageRequest<WordPressPage>(input, `/wp-json/wp/v2/pages/${pageId}?context=edit`);
}

export function createWordPressPageDraft(input: WordPressAuth, page: DashboardPageInput) {
  return wpPageRequest<WordPressPage>(input, "/wp-json/wp/v2/pages", { method: "POST", body: JSON.stringify(writeBody(page, "draft")) });
}

async function updateWordPressPage(input: WordPressAuth, pageId: number, page: DashboardPageInput, requiredStatus: "draft" | "publish") {
  const current = await getWordPressPage(input, pageId);
  if (current.status !== requiredStatus) {
    throw new Error(requiredStatus === "draft" ? "این برگه دیگر Draft نیست؛ صفحه را تازه‌سازی کنید." : "این برگه دیگر Published نیست؛ صفحه را تازه‌سازی کنید.");
  }
  return wpPageRequest<WordPressPage>(input, `/wp-json/wp/v2/pages/${pageId}`, { method: "POST", body: JSON.stringify(writeBody(page, requiredStatus)) });
}

export function updateWordPressPageDraft(input: WordPressAuth, pageId: number, page: DashboardPageInput) {
  return updateWordPressPage(input, pageId, page, "draft");
}

export function updateWordPressPublishedPage(input: WordPressAuth, pageId: number, page: DashboardPageInput) {
  return updateWordPressPage(input, pageId, page, "publish");
}

export async function publishWordPressPageDraft(input: WordPressAuth, pageId: number) {
  const current = await getWordPressPage(input, pageId);
  if (current.status !== "draft") throw new Error("فقط برگه‌ای که هنوز Draft است قابل انتشار از این عملیات است.");
  return wpPageRequest<WordPressPage>(input, `/wp-json/wp/v2/pages/${pageId}`, { method: "POST", body: JSON.stringify({ status: "publish" }) });
}
