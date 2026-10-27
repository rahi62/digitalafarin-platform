"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { db, initializeDatabase } from "@/lib/db";
import { getSiteConnection } from "@/lib/sites";
import {
  createWordPress301Redirect,
  deleteWordPressRedirect,
  permanentlyDeleteWordPressPost,
  setWordPressNoindex,
  trashWordPressPost,
} from "@/lib/wordpress";
import { requireAdmin } from "@/lib/session";

const siteIdSchema = z.string().uuid();
const postIdSchema = z.coerce.number().int().positive();
const redirectSourceSchema = z.string().trim().min(1).max(2048).refine((value) => value.startsWith("/") && !value.startsWith("//"), "Source باید یک مسیر نسبی مثل /old-page باشد.");
const redirectTargetSchema = z.string().trim().min(1).max(4096).refine((value) => {
  if (value.startsWith("/") && !value.startsWith("//")) return true;
  try { return ["http:", "https:"].includes(new URL(value).protocol); } catch { return false; }
}, "Target باید مسیر نسبی یا URL معتبر HTTP(S) باشد.");

async function audit(siteId: string, action: string, details: Record<string, unknown>) {
  await initializeDatabase();
  await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,$2,$3)", [siteId, action, JSON.stringify(details)]);
}

function refresh() {
  revalidatePath("/admin-tools");
  revalidatePath("/content");
  revalidatePath("/audit");
  revalidatePath("/");
}

export async function createRedirectAction(formData: FormData) {
  await requireAdmin();
  const siteId = siteIdSchema.parse(formData.get("siteId"));
  const source = redirectSourceSchema.parse(formData.get("source"));
  const target = redirectTargetSchema.parse(formData.get("target"));
  const site = await getSiteConnection(siteId);
  const redirect = await createWordPress301Redirect(site, source, target);
  await audit(siteId, "redirect.created", { redirectId: redirect.id, source: redirect.source, target: redirect.target, statusCode: 301 });
  refresh();
}

export async function deleteRedirectAction(formData: FormData) {
  await requireAdmin();
  const siteId = siteIdSchema.parse(formData.get("siteId"));
  const redirectId = z.string().uuid().parse(formData.get("redirectId"));
  const site = await getSiteConnection(siteId);
  const result = await deleteWordPressRedirect(site, redirectId);
  await audit(siteId, "redirect.deleted", { redirectId, source: result.redirect.source, target: result.redirect.target });
  refresh();
}

export async function setNoindexAction(formData: FormData) {
  await requireAdmin();
  const siteId = siteIdSchema.parse(formData.get("siteId"));
  const postId = postIdSchema.parse(formData.get("postId"));
  const noindex = z.enum(["true", "false"]).parse(String(formData.get("noindex"))) === "true";
  const site = await getSiteConnection(siteId);
  const indexing = await setWordPressNoindex(site, postId, noindex);
  await audit(siteId, "indexing.noindex_updated", { postId, noindex: indexing.noindex, status: indexing.status });
  refresh();
}

export async function trashPostAction(formData: FormData) {
  await requireAdmin();
  const siteId = siteIdSchema.parse(formData.get("siteId"));
  const postId = postIdSchema.parse(formData.get("postId"));
  const site = await getSiteConnection(siteId);
  const post = await trashWordPressPost(site, postId);
  await audit(siteId, "content.trashed", { postId, status: post.status, slug: post.slug });
  refresh();
}

export async function permanentlyDeletePostAction(formData: FormData) {
  await requireAdmin();
  const siteId = siteIdSchema.parse(formData.get("siteId"));
  const postId = postIdSchema.parse(formData.get("postId"));
  const confirmation = z.string().trim().min(1).max(100).parse(formData.get("confirmation"));
  const site = await getSiteConnection(siteId);
  const result = await permanentlyDeleteWordPressPost(site, postId, confirmation);
  await audit(siteId, "content.permanently_deleted", { postId, deleted: result.deleted, previousStatus: result.previous.status, slug: result.previous.slug });
  refresh();
}
