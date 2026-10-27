import assert from "node:assert/strict";
import test from "node:test";
import { ThemeTemplateClient } from "./theme-template-client.js";

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } });
}

const connection = { baseUrl: "https://example.test", username: "agent", appPassword: "app pass" };

test("status maps to the Bridge theme status route", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  let path = "";
  globalThis.fetch = async (input) => {
    path = new URL(String(input)).pathname;
    return json({ theme: { stylesheet: "x" } });
  };
  await new ThemeTemplateClient(connection).getStatus();
  assert.equal(path, "/wp-json/digitalafarin/v1/theme/status");
});

test("preview posts page binding, hash, and replacement to preview only", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  let request: { path: string; method?: string; body?: string } | undefined;
  globalThis.fetch = async (input, init) => {
    request = { path: new URL(String(input)).pathname, method: init?.method, body: String(init?.body ?? "") };
    return json({ eligible: true, proposedHash: "b".repeat(64) });
  };
  await new ThemeTemplateClient(connection).preview({
    pageId: 12,
    relativePath: "templates/pillar.php",
    expectedHash: "a".repeat(64),
    replacementContent: "<?php echo 1;",
  });
  assert.equal(request?.path, "/wp-json/digitalafarin/v1/theme/file/preview");
  assert.equal(request?.method, "POST");
  const body = JSON.parse(request!.body!);
  assert.equal(body.pageId, 12);
  assert.equal(body.expectedHash, "a".repeat(64));
});

test("update requires a proposed hash and maps to production update route", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  let path = "";
  globalThis.fetch = async (input) => {
    path = new URL(String(input)).pathname;
    return json({ written: true });
  };
  const client = new ThemeTemplateClient(connection);
  assert.throws(
    () => client.update({ pageId: 12, relativePath: "templates/pillar.php", expectedHash: "a".repeat(64), proposedHash: "", replacementContent: "<?php" }),
    /proposedHash/,
  );
  await client.update({
    pageId: 12,
    relativePath: "templates/pillar.php",
    expectedHash: "a".repeat(64),
    proposedHash: "b".repeat(64),
    replacementContent: "<?php",
    qaNeedles: ["H1"],
  });
  assert.equal(path, "/wp-json/digitalafarin/v1/theme/file/update");
});

test("restore requires current hash and posts to the backup restore route", async (t) => {
  const original = globalThis.fetch;
  t.after(() => { globalThis.fetch = original; });
  let request: { path: string; body?: string } | undefined;
  globalThis.fetch = async (input, init) => {
    request = { path: new URL(String(input)).pathname, body: String(init?.body ?? "") };
    return json({ restored: true });
  };
  await new ThemeTemplateClient(connection).restoreBackup(
    "123e4567-e89b-12d3-a456-426614174000",
    "c".repeat(64),
  );
  assert.equal(request?.path, "/wp-json/digitalafarin/v1/theme/backups/123e4567-e89b-12d3-a456-426614174000/restore");
  assert.equal(JSON.parse(request!.body!).expectedCurrentHash, "c".repeat(64));
});
