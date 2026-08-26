import { AddSiteForm } from "@/components/add-site-form";
import { logoutAction, toggleSiteAction } from "./actions";
import { db, initializeDatabase } from "@/lib/db";
import { requireAdmin } from "@/lib/session";

type Site = { id:string; name:string; base_url:string; username:string; enabled:boolean; last_check_status:string|null; last_check_message:string|null; last_checked_at:Date|null };

export default async function DashboardPage() {
  await requireAdmin(); await initializeDatabase();
  const result = await db.query<Site>("SELECT id,name,base_url,username,enabled,last_check_status,last_check_message,last_checked_at FROM wordpress_sites ORDER BY created_at DESC");
  const online = result.rows.filter((site) => site.enabled && site.last_check_status === "ok").length;
  return <main className="app-shell"><header className="topbar"><div><p className="eyebrow">DIGITALAFARIN</p><h1>WordPress Agent</h1></div><form action={logoutAction}><button className="ghost">خروج</button></form></header>
    <section className="stats"><article><span>سایت‌های ثبت‌شده</span><strong>{result.rowCount}</strong></article><article><span>اتصال فعال</span><strong>{online}</strong></article><article><span>عملیات در انتظار</span><strong>۰</strong></article></section>
    <div className="dashboard-grid"><section className="panel"><div className="panel-head"><div><p className="eyebrow">SITES</p><h2>سایت‌های وردپرسی</h2></div></div>
      <div className="site-list">{result.rows.length === 0 ? <div className="empty">هنوز سایتی اضافه نشده است.</div> : result.rows.map((site) => <article className="site-row" key={site.id}><div className={`status-dot ${site.enabled && site.last_check_status === "ok" ? "online" : ""}`} /><div className="site-copy"><strong>{site.name}</strong><a href={site.base_url} target="_blank" rel="noreferrer">{site.base_url}</a><small>{site.last_check_message ?? site.username}</small></div><form action={toggleSiteAction}><input type="hidden" name="id" value={site.id}/><button className="ghost">{site.enabled ? "غیرفعال‌سازی" : "فعال‌سازی"}</button></form></article>)}</div>
    </section><aside className="panel"><div className="panel-head"><div><p className="eyebrow">NEW CONNECTION</p><h2>افزودن سایت</h2></div></div><AddSiteForm/><p className="security-note">رمز برنامه پس از تست اتصال با AES-256-GCM رمزنگاری می‌شود و در رابط کاربری قابل مشاهده نیست.</p></aside></div>
  </main>;
}
