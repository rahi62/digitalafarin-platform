import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { GscOAuthLink } from "./gsc-oauth-link";

test("OAuth start uses a normal browser anchor instead of Next client navigation", () => {
  const html = renderToStaticMarkup(<GscOAuthLink className="button" label="Reconnect" />);

  assert.match(html, /^<a /);
  assert.match(html, /href="\/api\/gsc\/oauth\/start"/);
});
