"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import { db, initializeDatabase } from "@/lib/db";
import { requireAdmin } from "@/lib/session";
import { getSiteConnection } from "@/lib/sites";
import { createWordPressDraft, updateWordPressDraft } from "@/lib/wordpress";

export type ContentActionState = { error?: string; message?: string };

const draftSchema = z.object({
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
  const parsed = draftSchema.safeParse({
    siteId: formData.get("siteId"), title: formData.get("title"), content: formData.get("content"),
    excerpt: formData.get("excerpt") || undefined, slug: formData.get("slug") || undefined,
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "اطلاعات نوشته معتبر نیست." };
  try {
    const site = await getSiteConnection(parsed.data.siteId);
    const post = await createWordPressDraft(site, { ...parsed.data, categoryIds: categoryIds(formData) });
    await initializeDatabase();
    await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'content.draft_created',$2)", [site.id, JSON.stringify({ postId: post.id, title: parsed.data.title })]);
    revalidatePath("/content");
    redirect(`/content/${post.id}?siteId=${site.id}`);
  } catch (error) {
    if (error instanceof Error && error.message === "NEXT_REDIRECT") throw error;
    return { error: error instanceof Error ? error.message : "ساخت پیش‌نویس ناموفق بود." };
  }
}

export async function updateDraftAction(_state: ContentActionState, formData: FormData): Promise<ContentActionState> {
  await requireAdmin();
  const postId = Number(formData.get("postId"));
  if (!Number.isInteger(postId) || postId <= 0) return { error: "شناسه نوشته معتبر نیست." };
  const parsed = draftSchema.safeParse({
    siteId: formData.get("siteId"), title: formData.get("title"), content: formData.get("content"),
    excerpt: formData.get("excerpt") || undefined, slug: formData.get("slug") || undefined,
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "اطلاعات نوشته معتبر نیست." };
  try {
    const site = await getSiteConnection(parsed.data.siteId);
    await updateWordPressDraft(site, postId, { ...parsed.data, categoryIds: categoryIds(formData) });
    await initializeDatabase();
    await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'content.draft_updated',$2)", [site.id, JSON.stringify({ postId, title: parsed.data.title })]);
    revalidatePath("/content");
    revalidatePath(`/content/${postId}`);
    return { message: "پیش‌نویس با موفقیت ذخیره شد." };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "ذخیره پیش‌نویس ناموفق بود." };
  }
}
