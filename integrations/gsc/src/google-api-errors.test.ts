import test from "node:test";
import assert from "node:assert/strict";
import { googleRead } from "./google-api.js";

test("reports structured Google 403 without printing free-form messages", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => new Response(JSON.stringify({error:{status:"PERMISSION_DENIED",message:"sensitive@example.com",errors:[{reason:"accessNotConfigured"}]}}), {status:403,headers:{"content-type":"application/json"}});
  await assert.rejects(googleRead("dummy","https://www.googleapis.com/webmasters/v3/sites"), /reason=accessNotConfigured, status=PERMISSION_DENIED/);
});

test("recognizes non-JSON 403 responses", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  globalThis.fetch = async () => new Response("<html>Forbidden</html>", {status:403,headers:{"content-type":"text/html"}});
  await assert.rejects(googleRead("dummy","https://www.googleapis.com/webmasters/v3/sites"), /reason=non_json_html_response/);
});
