import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { ContentTabs } from "@/components/content-tabs";
import { requireAdmin } from "@/lib/session";
import { getSiteConnection, listSites } from "@/lib/sites";
import { listWordPressPosts } from "@/lib/wordpress";

const statusLabels: Record<string, string> = { publish: "منتشرشده", draft: "پیش‌نویس", pending: "در انتظار", private: "خصوصی", future: "زمان‌بندی‌شده" };

function cleanTitle(value: string) { return value.replace(/<[^>]*>/g, "").trim() || "بدون عنوان"; }

export default async function ContentPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await requireAdmin();
  const params = await searchParams;
  const sites = await listSites(true);
  const requestedSiteId = typeof params.siteId === "string" ? params.siteId : undefined;
  const selected = sites.find((site) => site.id === requestedSiteId) ?? sites[0];
  const status = typeof params.status === "string" && ["any", "draft", "publish", "pending", "private"].includes(params.status) ? params.status : "any";
  const query = typeof params.q === "string" ? params.q.slice(0, 200) : "";
  let posts: Awaited<ReturnType<typeof listWordPressPosts>> = [];
  let error = "";
  if (selected) {
    try {
      const connection = await getSiteConnection(selected.id);
      posts = await listWordPressPosts(connection, { status, search: query, perPage: 30 });
    } catch (cause) { error = cause instanceof Error ? cause.message : "دریافت محتوا ناموفق بود."; }
  }

  const actions = selected ? <Link className="button-link primary" href={`/content/new?siteId=${selected.id}`}>+ نوشته جدید</Link> : null;
  return <AppShell active="content" title="مدیریت محتوا" description="نوشته‌ها و برگه‌های WordPress را از یک Control Center مدیریت کنید." actions={actions}>
    {sites.length === 0 ? <section className="panel empty-state"><div className="empty-icon">◎</div><h2>سایت فعالی وجود ندارد</h2><p>ابتدا از بخش سایت‌ها یک اتصال فعال اضافه کنید.</p><Link className="button-link primary" href="/sites">رفتن به سایت‌ها</Link></section> : <>
      <ContentTabs active="posts" siteId={selected?.id}/>
      <section className="toolbar panel compact-panel">
        <form action="/content" method="get" className="filters">
          <label>سایت<select name="siteId" defaultValue={selected?.id}>{sites.map((site) => <option key={site.id} value={site.id}>{site.name}</option>)}</select></label>
          <label>وضعیت<select name="status" defaultValue={status}><option value="any">همه وضعیت‌ها</option><option value="publish">منتشرشده</option><option value="draft">پیش‌نویس</option><option value="pending">در انتظار</option><option value="private">خصوصی</option></select></label>
          <label className="search-field">جستجو<input name="q" defaultValue={query} placeholder="جستجو در عنوان و محتوا..." /></label>
          <button className="secondary filter-button" type="submit">اعمال فیلتر</button>
        </form>
      </section>
      {error ? <div className="error-banner"><strong>خطا در اتصال به وردپرس</strong><span>{error}</span></div> : <section className="panel content-panel">
        <div className="panel-head"><div><p className="eyebrow">POSTS LIBRARY</p><h2>{selected?.name}</h2></div><span className="count-pill">{posts.length} مورد</span></div>
        {posts.length === 0 ? <div className="empty">محتوایی مطابق این فیلتر پیدا نشد.</div> : <div className="content-table-wrap"><table className="content-table"><thead><tr><th>عنوان</th><th>وضعیت</th><th>آخرین ویرایش</th><th>عملیات</th></tr></thead><tbody>{posts.map((post) => <tr key={post.id}><td><div className="post-title"><strong>{cleanTitle(post.title.rendered)}</strong><small>#{post.id} · /{post.slug}</small></div></td><td><span className={`status-badge status-${post.status}`}>{statusLabels[post.status] ?? post.status}</span></td><td className="date-cell">{new Date(post.modified).toLocaleString("fa-IR")}</td><td><div className="row-actions">{post.status === "draft" || post.status === "publish" ? <Link className="text-link" href={`/content/${post.id}?siteId=${selected?.id}`}>{post.status === "publish" ? "ویرایش زنده" : "ویرایش"}</Link> : <span className="disabled-action">فقط خواندنی</span>}<a className="text-link subtle" href={post.link} target="_blank" rel="noreferrer">مشاهده</a></div></td></tr>)}</tbody></table></div>}
      </section>}
    </>}
  </AppShell>;
}
