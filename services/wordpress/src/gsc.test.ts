import assert from "node:assert/strict";
import test from "node:test";
import { listGscSitemaps } from "./gsc.js";

test("a valid access token reaches Google without a refresh exchange", async (t) => {
  const originalFetch = globalThis.fetch;
  const urls: string[] = [];
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (input) => {
    urls.push(String(input));
    return new Response(JSON.stringify({ sitemap: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  await listGscSitemaps("short-lived-access-token", "sc-domain:vammelki24.com");

  assert.equal(urls.length, 1);
  assert.match(urls[0] ?? "", /\/webmasters\/v3\/sites\//);
  assert.equal(urls.some((url) => url.includes("oauth2.googleapis.com/token")), false);
});
