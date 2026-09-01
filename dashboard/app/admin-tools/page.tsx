import { AppShell } from "@/components/app-shell";
import { listSites, getSiteConnection } from "@/lib/sites";
import { requireAdmin } from "@/lib/session";
import {
  checkWordPressConnection,
  getWordPressIndexing,
  getWordPressPost,
  listWordPressRedirects,
} from "@/lib/wordpress";
import {
  createRedirectAction,
  deleteRedirectAction,
  permanentlyDeletePostAction,
  setNoindexAction,
  trashPostAction,
} from "./actions";
import "./admin-tools.css";

export default async function AdminToolsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await requireAdmin();
  const params = await searchParams;
  const sites = await listSites(true);
  const requestedSiteId = typeof params.siteId === "string" ? params.siteId : "";
  const selectedSite = sites.find((site) => site.id === requestedSiteId) ?? sites[0];
  const requestedPostId = typeof params.postId === "string" && /^\d+$/.test(params.postId) ? Number(params.postId) : undefined;

  if (!selectedSite) {
    return <AppShell active="adminTools" title="ابزارهای ادمین و SEO" description="301 Redirect، Noindex و حذف کنترل‌شده محتوا."><div className="empty">ابتدا یک سایت فعال در پنل ثبت کنید.</div></AppShell>;
  }

  const connection = await getSiteConnection(selectedSite.id);
  const profile = await checkWordPressConnection(connection);
  const canManageRedirects = Boolean(profile.capabilities.manage_options);

  let redirects: Awaited<ReturnType<typeof listWordPressRedirects>> = [];
  let redirectError = "";
  try { redirects = await listWordPressRedirects(connection); }
  catch (error) { redirectError = error instanceof Error ? error.message : "خواندن Redirectها ناموفق بود."; }

  let inspectedPost: Awaited<ReturnType<typeof getWordPressPost>> | null = null;
  let indexing: Awaited<ReturnType<typeof getWordPressIndexing>> | null = null;
  let indexingError = "";
  if (requestedPostId) {
    try {
      [inspectedPost, indexing] = await Promise.all([
        getWordPressPost(connection, requestedPostId),
        getWordPressIndexing(connection, requestedPostId),
      ]);
    } catch (error) {
      indexingError = error instanceof Error ? error.message : "بررسی وضعیت ایندکس ناموفق بود.";
    }
  }

  const siteSelector = <form method="get" className="header-site-selector">
    <select name="siteId" defaultValue={selectedSite.id}>{sites.map((site) => <option value={site.id} key={site.id}>{site.name}</option>)}</select>
    <button className="secondary" type="submit">انتخاب سایت</button>
  </form>;

  return <AppShell active="adminTools" title="ابزارهای ادمین و SEO" description="کنترل Redirect، Indexing و حذف محتوا با guardهای مناسب برای عملیات حساس." actions={siteSelector}>
    <section className="admin-capability-grid">
      <article className="metric-card"><div className="metric-icon">WP</div><div><span>API User</span><strong className="metric-word">{profile.name || connection.username}</strong><small>{profile.roles.join(" · ") || "role نامشخص"}</small></div></article>
      <article className="metric-card"><div className={`metric-icon ${canManageRedirects ? "healthy" : "agent"}`}>{canManageRedirects ? "✓" : "!"}</div><div><span>Redirect capability</span><strong className="metric-word">{canManageRedirects ? "فعال" : "محدود"}</strong><small>{canManageRedirects ? "manage_options موجود است" : "برای Redirect نقش Administrator لازم است"}</small></div></article>
      <article className="metric-card security-metric"><div className="metric-icon secure">⌫</div><div><span>Delete policy</span><strong className="metric-word">دو مرحله‌ای</strong><small>Trash → Permanent confirmation</small></div></article>
    </section>

    <div className="admin-tool-grid">
      <section className="panel admin-tool-panel">
        <div className="panel-head"><div><p className="eyebrow">301 REDIRECTS</p><h2>مدیریت Redirect</h2></div><span className={`mini-badge ${canManageRedirects ? "enabled" : "disabled"}`}>{canManageRedirects ? "Admin access" : "نیازمند Administrator"}</span></div>
        <p className="tool-copy">Redirectها توسط DigitalAfarin Agent Bridge اجرا می‌شوند و به Yoast Premium یا Rank Math Pro وابسته نیستند. Source به صورت exact path نگهداری می‌شود.</p>
        {redirectError && <div className="error-banner"><strong>Redirect Bridge در دسترس نیست</strong><span>{redirectError}</span></div>}
        <form action={createRedirectAction} className="redirect-create-form">
          <input type="hidden" name="siteId" value={selectedSite.id}/>
          <label>Source path<input name="source" dir="ltr" placeholder="/old-page" required /></label>
          <label>Target<input name="target" dir="ltr" placeholder="/new-page یا https://example.com/new" required /></label>
          <button className="primary" type="submit" disabled={!canManageRedirects}>ساخت Redirect 301</button>
        </form>
        <div className="redirect-list">
          {redirects.length === 0 ? <div className="empty compact-empty">Redirect ثبت‌شده‌ای وجود ندارد.</div> : redirects.map((redirect) => <article className="redirect-row" key={redirect.id}>
            <div><strong dir="ltr">{redirect.source}</strong><span>→</span><a dir="ltr" href={redirect.target} target="_blank" rel="noreferrer">{redirect.target}</a></div>
            <form action={deleteRedirectAction}><input type="hidden" name="siteId" value={selectedSite.id}/><input type="hidden" name="redirectId" value={redirect.id}/><button className="ghost danger-button" type="submit">حذف Redirect</button></form>
          </article>)}
        </div>
      </section>

      <section className="panel admin-tool-panel">
        <div className="panel-head"><div><p className="eyebrow">INDEX CONTROL</p><h2>Noindex کنترل‌شده</h2></div></div>
        <p className="tool-copy">Noindex روی Draft یا Published اعمال می‌شود. روی نوشته منتشرشده تغییر بلافاصله در robots output سایت اثر می‌گذارد.</p>
        <form method="get" className="inspect-form">
          <input type="hidden" name="siteId" value={selectedSite.id}/>
          <label>Post ID<input name="postId" inputMode="numeric" dir="ltr" defaultValue={requestedPostId ?? ""} placeholder="12968" required /></label>
          <button className="secondary" type="submit">بررسی وضعیت</button>
        </form>
        {indexingError && <div className="error-banner"><span>{indexingError}</span></div>}
        {inspectedPost && indexing && <div className="indexing-status-card">
          <div><span>نوشته</span><strong>{inspectedPost.title.raw ?? inspectedPost.title.rendered}</strong><small>#{inspectedPost.id} · {inspectedPost.status}</small></div>
          <span className={`mini-badge ${indexing.noindex ? "disabled" : "enabled"}`}>{indexing.noindex ? "NOINDEX" : "Indexable"}</span>
        </div>}
        {requestedPostId && <div className="dual-actions">
          <form action={setNoindexAction}><input type="hidden" name="siteId" value={selectedSite.id}/><input type="hidden" name="postId" value={requestedPostId}/><input type="hidden" name="noindex" value="true"/><button className="warning-button" type="submit">اعمال Noindex</button></form>
          <form action={setNoindexAction}><input type="hidden" name="siteId" value={selectedSite.id}/><input type="hidden" name="postId" value={requestedPostId}/><input type="hidden" name="noindex" value="false"/><button className="secondary" type="submit">حذف Noindex</button></form>
        </div>}
      </section>
    </div>

    <section className="panel danger-admin-panel">
      <div className="panel-head"><div><p className="eyebrow">DESTRUCTIVE OPERATIONS</p><h2>حذف محتوا</h2></div><span className="mini-badge disabled">حساس</span></div>
      <div className="delete-policy"><strong>سیاست دو مرحله‌ای</strong><p>عملیات عادی فقط نوشته را به Trash می‌برد. حذف دائمی فقط وقتی مجاز است که Post از قبل داخل Trash باشد و عبارت تأیید دقیق وارد شود.</p></div>
      <div className="delete-grid">
        <form action={trashPostAction} className="danger-form">
          <h3>انتقال به Trash</h3><p>قابل بازیابی از WordPress است ولی URL از انتشار خارج می‌شود.</p>
          <input type="hidden" name="siteId" value={selectedSite.id}/><label>Post ID<input name="postId" inputMode="numeric" dir="ltr" required /></label>
          <button className="warning-button" type="submit">Move to Trash</button>
        </form>
        <form action={permanentlyDeletePostAction} className="danger-form permanent-box">
          <h3>حذف دائمی</h3><p>غیرقابل بازگشت. Post باید ابتدا در Trash باشد.</p>
          <input type="hidden" name="siteId" value={selectedSite.id}/><label>Post ID<input name="postId" inputMode="numeric" dir="ltr" required /></label>
          <label>Confirmation<input name="confirmation" dir="ltr" placeholder="PERMANENTLY DELETE POST 123" required /></label>
          <button className="danger-solid" type="submit">Delete Permanently</button>
        </form>
      </div>
    </section>
  </AppShell>;
}
