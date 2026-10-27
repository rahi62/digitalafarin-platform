import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { ContentTabs } from "@/components/content-tabs";
import { requireAdmin } from "@/lib/session";
import { getSiteConnection, listSites } from "@/lib/sites";
import { listWordPressPages } from "@/lib/pages";

const statusLabels: Record<string, string> = { publish: "منتشرشده", draft: "پیش‌نویس", pending: "در انتظار", private: "خصوصی", future: "زمان‌بندی‌شده" };
function cleanTitle(value: string) { return value.replace(/<[^>]*>/g, "").trim() || "بدون عنوان"; }

export default async function PagesPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await requireAdmin();
  const params = await searchParams;
  const sites = await listSites(true);
  const requestedSiteId = typeof params.siteId === "string" ? params.siteId : undefined;
  const selected = sites.find((site) => site.id === requestedSiteId) ?? sites[0];
  const status = typeof params.status === "string" && ["any", "draft", "publish", "pending", "private"].includes(params.status) ? params.status : "any";
  const query = typeof params.q === "string" ? params.q.slice(0, 200) : "";
  let pages: Awaited<ReturnType<typeof listWordPressPages>> = [];
  let error = "";
  if (selected) {
    try {
      const connection = await getSiteConnection(selected.id);
      pages = await listWordPressPages(connection, { status, search: query, perPage: 30 });
    } catch (cause) { error = cause instanceof Error ? cause.message : "دریافت برگه‌ها ناموفق بود."; }
  }

  const actions = selected ? <Link className="button-link primary" href={`/pages/new?siteId=${selected.id}`}>+ برگه جدید</Link> : null;
  return <AppShell active="content" title="مدیریت محتوا" description="نوشته‌ها و برگه‌های WordPress را از یک Control Center مدیریت کنید." actions={actions}>
    {sites.length === 0 ? <section className="panel empty-state"><div className="empty-icon">◎</div><h2>سایت فعالی وجود ندارد</h2><p>ابتدا از بخش سایت‌ها یک اتصال فعال اضافه کنید.</p><Link className="button-link primary" href="/sites">رفتن به سایت‌ها</Link></section> : <>
      <ContentTabs active="pages" siteId={selected?.id}/>
      <section className="toolbar panel compact-panel">
        <form action="/pages" method="get" className="filters">
          <label>سایت<select name="siteId" defaultValue={selected?.id}>{sites.map((site) => <option key={site.id} value={site.id}>{site.name}</option>)}</select></label>
          <label>وضعیت<select name="status" defaultValue={status}><option value="any">همه وضعیت‌ها</option><option value="publish">منتشرشده</option><option value="draft">پیش‌نویس</option><option value="pending">در انتظار</option><option value="private">خصوصی</option></select></label>
          <label className="search-field">جستجو<input name="q" defaultValue={query} placeholder="جستجو در عنوان و محتوا..." /></label>
          <button className="secondary filter-button" type="submit">اعمال فیلتر</button>
        </form>
      </section>
      {error ? <div className="error-banner"><strong>خطا در اتصال به WordPress Pages</strong><span>{error}</span></div> : <section className="panel content-panel">
        <div className="panel-head"><div><p className="eyebrow">PAGES LIBRARY</p><h2>{selected?.name}</h2></div><span className="count-pill">{pages.length} برگه</span></div>
        {pages.length === 0 ? <div className="empty">برگه‌ای مطابق این فیلتر پیدا نشد.</div> : <div className="content-table-wrap"><table className="content-table"><thead><tr><th>عنوان</th><th>وضعیت</th><th>Parent / Template</th><th>آخرین ویرایش</th><th>عملیات</th></tr></thead><tbody>{pages.map((page) => <tr key={page.id}><td><div className="post-title"><strong>{cleanTitle(page.title.rendered)}</strong><small>#{page.id} · /{page.slug}</small></div></td><td><span className={`status-badge status-${page.status}`}>{statusLabels[page.status] ?? page.status}</span></td><td><small>parent #{page.parent || 0}<br/>{page.template || "default"}</small></td><td className="date-cell">{new Date(page.modified).toLocaleString("fa-IR")}</td><td><div className="row-actions">{page.status === "draft" || page.status === "publish" ? <Link className="text-link" href={`/pages/${page.id}?siteId=${selected?.id}`}>{page.status === "publish" ? "ویرایش زنده" : "ویرایش"}</Link> : <span className="disabled-action">فقط خواندنی</span>}<a className="text-link subtle" href={page.link} target="_blank" rel="noreferrer">مشاهده</a></div></td></tr>)}</tbody></table></div>}
      </section>}
    </>}
  </AppShell>;
}
