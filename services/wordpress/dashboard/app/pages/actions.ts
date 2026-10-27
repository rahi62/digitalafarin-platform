"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import { db, initializeDatabase } from "@/lib/db";
import { requireAdmin } from "@/lib/session";
import { getSiteConnection } from "@/lib/sites";
import { createWordPressPageDraft, getWordPressPage, publishWordPressPageDraft, updateWordPressPageDraft, updateWordPressPublishedPage } from "@/lib/pages";

export type PageActionState = { error?: string; message?: string };

const pageSchema = z.object({
  siteId: z.string().uuid(),
  title: z.string().trim().min(1, "عنوان الزامی است.").max(500),
  content: z.string().min(1, "محتوا نمی‌تواند خالی باشد."),
  slug: z.string().trim().max(200).regex(/^[a-z0-9-]*$/, "اسلاگ فقط می‌تواند شامل حروف انگلیسی کوچک، عدد و خط تیره باشد.").optional(),
  parent: z.coerce.number().int().min(0).optional(),
  menuOrder: z.coerce.number().int().min(0).max(1_000_000).optional(),
  template: z.string().trim().max(255).optional(),
});

function parse(formData: FormData) {
  return pageSchema.safeParse({
    siteId: formData.get("siteId"),
    title: formData.get("title"),
    content: formData.get("content"),
    slug: formData.get("slug") || undefined,
    parent: formData.get("parent") || 0,
    menuOrder: formData.get("menuOrder") || 0,
    template: formData.get("template") || undefined,
  });
}

export async function createPageDraftAction(_state: PageActionState, formData: FormData): Promise<PageActionState> {
  await requireAdmin();
  const parsed = parse(formData);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "اطلاعات برگه معتبر نیست." };
  let destination = "";
  try {
    const site = await getSiteConnection(parsed.data.siteId);
    const page = await createWordPressPageDraft(site, parsed.data);
    await initializeDatabase();
    await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'content.page_draft_created',$2)", [site.id, JSON.stringify({ pageId: page.id, title: parsed.data.title })]);
    revalidatePath("/pages");
    destination = `/pages/${page.id}?siteId=${site.id}`;
  } catch (error) {
    return { error: error instanceof Error ? error.message : "ساخت پیش‌نویس برگه ناموفق بود." };
  }
  redirect(destination);
}

export async function updatePageAction(_state: PageActionState, formData: FormData): Promise<PageActionState> {
  await requireAdmin();
  const pageId = Number(formData.get("pageId"));
  if (!Number.isInteger(pageId) || pageId <= 0) return { error: "شناسه برگه معتبر نیست." };
  const parsed = parse(formData);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "اطلاعات برگه معتبر نیست." };
  try {
    const site = await getSiteConnection(parsed.data.siteId);
    const current = await getWordPressPage(site, pageId);
    if (current.status === "draft") await updateWordPressPageDraft(site, pageId, parsed.data);
    else if (current.status === "publish") await updateWordPressPublishedPage(site, pageId, parsed.data);
    else return { error: `وضعیت ${current.status} از پنل قابل ویرایش نیست.` };
    await initializeDatabase();
    await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,$2,$3)", [site.id, current.status === "publish" ? "content.page_updated" : "content.page_draft_updated", JSON.stringify({ pageId, title: parsed.data.title, live: current.status === "publish" })]);
    revalidatePath("/pages");
    revalidatePath(`/pages/${pageId}`);
    return { message: current.status === "publish" ? "تغییرات روی برگه منتشرشده اعمال شد." : "پیش‌نویس برگه ذخیره شد." };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "ذخیره برگه ناموفق بود." };
  }
}

export async function publishPageDraftAction(formData: FormData) {
  await requireAdmin();
  const siteId = z.string().uuid().parse(formData.get("siteId"));
  const pageId = Number(formData.get("pageId"));
  if (!Number.isInteger(pageId) || pageId <= 0) throw new Error("شناسه برگه معتبر نیست.");
  const site = await getSiteConnection(siteId);
  const page = await publishWordPressPageDraft(site, pageId);
  await initializeDatabase();
  await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'content.page_published',$2)", [site.id, JSON.stringify({ pageId, title: page.title.raw || page.title.rendered })]);
  revalidatePath("/pages");
  revalidatePath(`/pages/${pageId}`);
  redirect(`/pages/${pageId}?siteId=${site.id}`);
}
