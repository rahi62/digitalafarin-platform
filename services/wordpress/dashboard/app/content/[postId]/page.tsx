import Link from "next/link";
import { publishDraftAction } from "@/app/content/actions";
import { AppShell } from "@/components/app-shell";
import { DraftForm } from "@/components/draft-form";
import { requireAdmin } from "@/lib/session";
import { getSiteConnection, listSites } from "@/lib/sites";
import { getWordPressPost, listWordPressCategories } from "@/lib/wordpress";

export default async function EditPostPage({ params, searchParams }: { params: Promise<{ postId: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await requireAdmin();
  const { postId: rawPostId } = await params;
  const query = await searchParams;
  const postId = Number(rawPostId);
  if (!Number.isInteger(postId) || postId <= 0) throw new Error("شناسه نوشته معتبر نیست.");
  const sites = await listSites(true);
  const requestedSiteId = typeof query.siteId === "string" ? query.siteId : undefined;
  const selected = sites.find((site) => site.id === requestedSiteId) ?? sites[0];
  if (!selected) return <AppShell active="content" title="ویرایش نوشته"><section className="panel empty-state"><h2>سایت فعالی وجود ندارد</h2></section></AppShell>;
  const connection = await getSiteConnection(selected.id);
  const [post, categories] = await Promise.all([getWordPressPost(connection, postId), listWordPressCategories(connection).catch(() => [])]);
  const title = post.title.raw || post.title.rendered.replace(/<[^>]*>/g, "") || "بدون عنوان";
  const supported = post.status === "draft" || post.status === "publish";
  const actions = <div className="site-actions">
    {post.status === "draft" && <form action={publishDraftAction}><input type="hidden" name="siteId" value={selected.id}/><input type="hidden" name="postId" value={post.id}/><button className="primary" type="submit">انتشار Draft</button></form>}
    <Link className="button-link secondary" href={`/content?siteId=${selected.id}`}>بازگشت به محتوا</Link>
  </div>;

  if (!supported) return <AppShell active="content" title={title} description={`وضعیت ${post.status} در این نسخه از پنل فقط خواندنی است.`} actions={actions}>
    <section className="panel readonly-panel"><div className="readonly-icon">🔒</div><div><h2>ویرایش این وضعیت پشتیبانی نمی‌شود</h2><p>پنل برای Draft و Published امکان ویرایش دارد؛ Pending، Private و Scheduled فعلاً فقط خواندنی هستند.</p><a className="button-link secondary" href={post.link} target="_blank" rel="noreferrer">مشاهده در سایت</a></div></section>
  </AppShell>;

  return <AppShell active="content" title={title} description={post.status === "publish" ? `ویرایش زنده نوشته #${post.id} در ${selected.name}` : `ویرایش پیش‌نویس #${post.id} در ${selected.name}`} actions={actions}>
    <DraftForm siteId={selected.id} categories={categories} values={{ postId: post.id, status: post.status, title: post.title.raw || title, content: post.content.raw || post.content.rendered, excerpt: post.excerpt.raw || "", slug: post.slug, categoryIds: post.categories }} />
  </AppShell>;
}
