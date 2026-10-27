import { readFileSync, existsSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const layoutPath = new URL("../app/layout.tsx", import.meta.url);
const sidebarPath = new URL("../components/app-sidebar.tsx", import.meta.url);
const cssPath = new URL("../app/globals.css", import.meta.url);

test("admin root is Persian-first and RTL-first", () => {
  assert.equal(existsSync(layoutPath), true, "admin/app/layout.tsx must exist");
  const source = readFileSync(layoutPath, "utf8");
  assert.match(source, /lang=["']fa["']/);
  assert.match(source, /dir=["']rtl["']/);
});

test("admin has a reusable right-side application sidebar", () => {
  assert.equal(existsSync(sidebarPath), true, "admin/components/app-sidebar.tsx must exist");
  const source = readFileSync(sidebarPath, "utf8");
  assert.match(source, /پروژه‌ها/);
  assert.match(source, /تأییدها/);
  assert.match(source, /اتصال‌ها/);
});

test("admin layout CSS uses logical properties for RTL layout", () => {
  assert.equal(existsSync(cssPath), true, "admin/app/globals.css must exist");
  const source = readFileSync(cssPath, "utf8");
  assert.match(source, /padding-inline/);
  assert.match(source, /inset-inline/);
  assert.doesNotMatch(source, /margin-left\s*:|margin-right\s*:|padding-left\s*:|padding-right\s*:/);
});
