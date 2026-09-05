import Link from "next/link";
import { publishPageDraftAction } from "@/app/pages/actions";
import { AppShell } from "@/components/app-shell";
import { PageForm } from "@/components/page-form";
import { requireAdmin } from "@/lib/session";
import { getSiteConnection, listSites } from "@/lib/sites";
import { getWordPressPage } from "@/lib/pages";

export default async function EditPagePage({ params, searchParams }: { params: Promise<{ pageId: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await requireAdmin();
  const { pageId: rawPageId } = await params;
  const query = await searchParams;
  const pageId = Number(rawPageId);
  if (!Number.isInteger(pageId) || pageId <= 0) throw new Error("شناسه برگه معتبر نیست.");
  const sites = await listSites(true);
  const requestedSiteId = typeof query.siteId === "string" ? query.siteId : undefined;
  const selected = sites.find((site) => site.id === requestedSiteId) ?? sites[0];
  if (!selected) return <AppShell active="content" title="ویرایش برگه"><section className="panel empty-state"><h2>سایت فعالی وجود ندارد</h2></section></AppShell>;
  const connection = await getSiteConnection(selected.id);
  const page = await getWordPressPage(connection, pageId);
  const title = page.title.raw || page.title.rendered.replace(/<[^>]*>/g, "") || "بدون عنوان";
  const supported = page.status === "draft" || page.status === "publish";
  const actions = <div className="site-actions">
    {page.status === "draft" && <form action={publishPageDraftAction}><input type="hidden" name="siteId" value={selected.id}/><input type="hidden" name="pageId" value={page.id}/><button className="primary" type="submit">انتشار Draft</button></form>}
    <Link className="button-link secondary" href={`/pages?siteId=${selected.id}`}>بازگشت به برگه‌ها</Link>
  </div>;

  if (!supported) return <AppShell active="content" title={title} description={`وضعیت ${page.status} در این نسخه فقط خواندنی است.`} actions={actions}>
    <section className="panel readonly-panel"><div className="readonly-icon">🔒</div><div><h2>ویرایش این وضعیت پشتیبانی نمی‌شود</h2><p>Draft و Published قابل ویرایش‌اند؛ سایر وضعیت‌ها فعلاً فقط خواندنی هستند.</p><a className="button-link secondary" href={page.link} target="_blank" rel="noreferrer">مشاهده در سایت</a></div></section>
  </AppShell>;

  return <AppShell active="content" title={title} description={page.status === "publish" ? `ویرایش زنده برگه #${page.id} در ${selected.name}` : `ویرایش پیش‌نویس برگه #${page.id} در ${selected.name}`} actions={actions}>
    <PageForm siteId={selected.id} values={{ pageId: page.id, status: page.status, title: page.title.raw || title, content: page.content.raw || page.content.rendered, slug: page.slug, parent: page.parent, menuOrder: page.menu_order, template: page.template }} />
  </AppShell>;
}
