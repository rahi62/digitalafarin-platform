"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import { db, initializeDatabase } from "@/lib/db";
import { requireAdmin } from "@/lib/session";
import { getSiteConnection } from "@/lib/sites";
import { createWordPressDraft, getWordPressPost, publishWordPressDraft, updateWordPressDraft, updateWordPressPublishedPost } from "@/lib/wordpress";

export type ContentActionState = { error?: string; message?: string };

const postSchema = z.object({
  siteId: z.string().uuid(),
  title: z.string().trim().min(1, "عنوان الزامی است.").max(500),
  content: z.string().min(1, "محتوا نمی‌تواند خالی باشد."),
  excerpt: z.string().max(5000).optional(),
  slug: z.string().trim().max(200).regex(/^[a-z0-9-]*$/, "اسلاگ فقط می‌تواند شامل حروف انگلیسی کوچک، عدد و خط تیره باشد.").optional(),
});

function categoryIds(formData: FormData) {
  return formData.getAll("categoryIds").map((value) => Number(value)).filter((value) => Number.isInteger(value) && value > 0).slice(0, 20);
}

export async function createDraftAction(_state: ContentActionState, formData: FormData): Promise<ContentActionState> {
  await requireAdmin();
  const parsed = postSchema.safeParse({
    siteId: formData.get("siteId"), title: formData.get("title"), content: formData.get("content"),
    excerpt: formData.get("excerpt") || undefined, slug: formData.get("slug") || undefined,
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "اطلاعات نوشته معتبر نیست." };

  let destination = "";
  try {
    const site = await getSiteConnection(parsed.data.siteId);
    const post = await createWordPressDraft(site, { ...parsed.data, categoryIds: categoryIds(formData) });
    await initializeDatabase();
    await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'content.draft_created',$2)", [site.id, JSON.stringify({ postId: post.id, title: parsed.data.title })]);
    revalidatePath("/content");
    destination = `/content/${post.id}?siteId=${site.id}`;
  } catch (error) {
    return { error: error instanceof Error ? error.message : "ساخت پیش‌نویس ناموفق بود." };
  }
  redirect(destination);
}

export async function updatePostAction(_state: ContentActionState, formData: FormData): Promise<ContentActionState> {
  await requireAdmin();
  const postId = Number(formData.get("postId"));
  if (!Number.isInteger(postId) || postId <= 0) return { error: "شناسه نوشته معتبر نیست." };
  const parsed = postSchema.safeParse({
    siteId: formData.get("siteId"), title: formData.get("title"), content: formData.get("content"),
    excerpt: formData.get("excerpt") || undefined, slug: formData.get("slug") || undefined,
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "اطلاعات نوشته معتبر نیست." };
  try {
    const site = await getSiteConnection(parsed.data.siteId);
    const current = await getWordPressPost(site, postId);
    if (current.status === "draft") {
      await updateWordPressDraft(site, postId, { ...parsed.data, categoryIds: categoryIds(formData) });
    } else if (current.status === "publish") {
      await updateWordPressPublishedPost(site, postId, { ...parsed.data, categoryIds: categoryIds(formData) });
    } else {
      return { error: `وضعیت ${current.status} از پنل قابل ویرایش نیست.` };
    }
    await initializeDatabase();
    await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,$2,$3)", [site.id, current.status === "publish" ? "content.post_updated" : "content.draft_updated", JSON.stringify({ postId, title: parsed.data.title, live: current.status === "publish" })]);
    revalidatePath("/content");
    revalidatePath(`/content/${postId}`);
    return { message: current.status === "publish" ? "تغییرات روی نوشته منتشرشده اعمال شد." : "پیش‌نویس با موفقیت ذخیره شد." };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "ذخیره نوشته ناموفق بود." };
  }
}

export async function publishDraftAction(formData: FormData) {
  await requireAdmin();
  const siteId = z.string().uuid().parse(formData.get("siteId"));
  const postId = Number(formData.get("postId"));
  if (!Number.isInteger(postId) || postId <= 0) throw new Error("شناسه نوشته معتبر نیست.");
  const site = await getSiteConnection(siteId);
  const post = await publishWordPressDraft(site, postId);
  await initializeDatabase();
  await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'content.published',$2)", [site.id, JSON.stringify({ postId, title: post.title.raw || post.title.rendered })]);
  revalidatePath("/content");
  revalidatePath(`/content/${postId}`);
  redirect(`/content/${postId}?siteId=${site.id}`);
}
