import assert from "node:assert/strict";
import test from "node:test";
import { WordPressPageClient } from "./page-client.js";
import { WordPressError } from "./wordpress.js";

function page(overrides: Record<string, unknown> = {}) {
  return {
    id: 12,
    date: "2026-09-05T10:00:00",
    modified: "2026-09-05T10:00:00",
    slug: "loan-page",
    status: "publish",
    link: "https://example.com/loan-page/",
    title: { raw: "Loan page", rendered: "Loan page" },
    content: { raw: "<p>Body</p>", rendered: "<p>Body</p>" },
    featured_media: 0,
    parent: 0,
    menu_order: 0,
    template: "",
    yoast_head_json: {},
    ...overrides,
  };
}

function client() {
  return new WordPressPageClient({ baseUrl: "https://example.com", username: "agent", appPassword: "app pass" });
}

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

test("listPages reads editable pages from wp/v2/pages", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  let requestedUrl = "";
  globalThis.fetch = async (input) => { requestedUrl = String(input); return jsonResponse([]); };

  await client().listPages({ search: "وام", page: 2, perPage: 25, status: "publish" });

  const url = new URL(requestedUrl);
  assert.equal(url.pathname, "/wp-json/wp/v2/pages");
  assert.equal(url.searchParams.get("context"), "edit");
  assert.equal(url.searchParams.get("search"), "وام");
  assert.equal(url.searchParams.get("page"), "2");
  assert.equal(url.searchParams.get("per_page"), "25");
  assert.equal(url.searchParams.get("status"), "publish");
});

test("createPageDraft always creates a draft page with page fields", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  let request: { url: string; init?: RequestInit } | undefined;
  globalThis.fetch = async (input, init) => { request = { url: String(input), init }; return jsonResponse(page({ status: "draft" }), 201); };

  await client().createPageDraft({ title: "وام آزاد فوری", content: "<p>content</p>", slug: "vam-azad-fori", parent: 7, menuOrder: 3, template: "template-loan.php" });

  assert.ok(request);
  assert.equal(new URL(request!.url).pathname, "/wp-json/wp/v2/pages");
  assert.equal(request!.init?.method, "POST");
  const body = JSON.parse(String(request!.init?.body));
  assert.equal(body.status, "draft");
  assert.equal(body.parent, 7);
  assert.equal(body.menu_order, 3);
  assert.equal(body.template, "template-loan.php");
});

test("updatePublishedPage preserves publish status and honors expectedModified", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input, init) => { calls.push({ url: String(input), init }); return calls.length === 1 ? jsonResponse(page()) : jsonResponse(page({ title: { raw: "Updated", rendered: "Updated" } })); };

  await client().updatePublishedPage(12, { title: "Updated" }, "2026-09-05T10:00:00");

  assert.equal(new URL(calls[0]!.url).pathname, "/wp-json/wp/v2/pages/12");
  assert.equal(new URL(calls[1]!.url).pathname, "/wp-json/wp/v2/pages/12");
  assert.equal(calls[1]!.init?.method, "POST");
  const body = JSON.parse(String(calls[1]!.init?.body));
  assert.equal(body.status, "publish");
  assert.equal(body.title, "Updated");
});

test("updatePublishedPage refuses a non-published page", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async () => jsonResponse(page({ status: "draft" }));

  await assert.rejects(() => client().updatePublishedPage(12, { title: "Nope" }), (error: unknown) => error instanceof WordPressError && error.code === "not_published_page");
});

test("setPageFeaturedImage writes featured_media through wp/v2/pages", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input, init) => { calls.push({ url: String(input), init }); return jsonResponse(page()); };

  await client().setPageFeaturedImage(12, 77, "2026-09-05T10:00:00");

  assert.equal(new URL(calls[1]!.url).pathname, "/wp-json/wp/v2/pages/12");
  const body = JSON.parse(String(calls[1]!.init?.body));
  assert.equal(body.featured_media, 77);
  assert.equal(body.status, "publish");
});

test("page SEO and noindex validate the page through wp/v2/pages before Bridge writes", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  const paths: string[] = [];
  globalThis.fetch = async (input) => {
    const url = new URL(String(input));
    paths.push(url.pathname);
    if (url.pathname === "/wp-json/wp/v2/pages/12") return jsonResponse(page());
    if (url.pathname.endsWith("/seo")) return jsonResponse({ provider: "yoast", writable: true, status: "publish", fields: {} });
    if (url.pathname.endsWith("/indexing")) return jsonResponse({ postId: 12, status: "publish", noindex: true, source: "digitalafarin-bridge" });
    return jsonResponse({});
  };

  await client().updatePageSeo(12, { title: "SEO title" }, "2026-09-05T10:00:00");
  await client().setPageNoindex(12, true, "2026-09-05T10:00:00");

  assert.deepEqual(paths, ["/wp-json/wp/v2/pages/12", "/wp-json/digitalafarin/v1/posts/12/seo", "/wp-json/wp/v2/pages/12", "/wp-json/digitalafarin/v1/posts/12/indexing"]);
});
