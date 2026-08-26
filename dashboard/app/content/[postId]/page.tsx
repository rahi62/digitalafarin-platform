import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { DraftForm } from "@/components/draft-form";
import { requireAdmin } from "@/lib/session";
import { getSiteConnection, listSites } from "@/lib/sites";
import { getWordPressPost, listWordPressCategories } from "@/lib/wordpress";

export default async function EditDraftPage({ params, searchParams }: { params: Promise<{ postId: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
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
  const back = <Link className="button-link secondary" href={`/content?siteId=${selected.id}`}>بازگشت به محتوا</Link>;
  if (post.status !== "draft") return <AppShell active="content" title={title} description="این نوشته منتشرشده یا غیردرافت است و در حالت امن فقط خواندنی نمایش داده می‌شود." actions={back}>
    <section className="panel readonly-panel"><div className="readonly-icon">🔒</div><div><h2>ویرایش این نوشته قفل است</h2><p>برای جلوگیری از تغییر ناخواسته محتوای زنده، نسخه فعلی پنل فقط Draftها را ویرایش می‌کند.</p><a className="button-link secondary" href={post.link} target="_blank" rel="noreferrer">مشاهده در سایت</a></div></section>
  </AppShell>;
  return <AppShell active="content" title={title} description={`ویرایش پیش‌نویس #${post.id} در ${selected.name}`} actions={back}>
    <DraftForm siteId={selected.id} categories={categories} values={{ postId: post.id, title: post.title.raw || title, content: post.content.raw || post.content.rendered, excerpt: post.excerpt.raw || "", slug: post.slug, categoryIds: post.categories }} />
  </AppShell>;
}
