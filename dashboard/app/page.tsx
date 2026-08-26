import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { db, initializeDatabase } from "@/lib/db";
import { requireAdmin } from "@/lib/session";
import { listSites } from "@/lib/sites";

type AuditRow = { id: string; action: string; created_at: Date; site_name: string | null; details: Record<string, unknown> };

const actionLabels: Record<string, string> = {
  "site.created": "سایت جدید اضافه شد", "site.toggled": "وضعیت سایت تغییر کرد", "site.health_checked": "اتصال سایت بررسی شد",
  "agent.site_resolved": "Agent به سایت دسترسی گرفت", "content.draft_created": "پیش‌نویس جدید ساخته شد", "content.draft_updated": "پیش‌نویس ویرایش شد",
};

export default async function DashboardPage() {
  await requireAdmin(); await initializeDatabase();
  const sites = await listSites(false);
  const enabled = sites.filter((site) => site.enabled).length;
  const healthy = sites.filter((site) => site.enabled && site.last_check_status === "ok").length;
  const auditResult = await db.query<AuditRow>(`SELECT a.id::text,a.action,a.created_at,a.details,s.name AS site_name FROM audit_logs a LEFT JOIN wordpress_sites s ON s.id=a.site_id ORDER BY a.created_at DESC LIMIT 8`);
  const agentOps = await db.query<{ count: string }>("SELECT COUNT(*)::text AS count FROM audit_logs WHERE action='agent.site_resolved' AND created_at >= NOW() - INTERVAL '24 hours'");
  return <AppShell active="dashboard" title="داشبورد" description="مرکز کنترل سایت‌های وردپرسی، محتوا و دسترسی Agent.">
    <section className="metric-grid">
      <article className="metric-card"><div className="metric-icon">◎</div><div><span>سایت‌های ثبت‌شده</span><strong>{sites.length}</strong><small>{enabled} سایت فعال</small></div></article>
      <article className="metric-card"><div className="metric-icon healthy">✓</div><div><span>اتصال سالم</span><strong>{healthy}</strong><small>از {enabled} اتصال فعال</small></div></article>
      <article className="metric-card"><div className="metric-icon agent">✦</div><div><span>دسترسی Agent / 24h</span><strong>{agentOps.rows[0]?.count ?? "0"}</strong><small>ثبت‌شده در Audit Log</small></div></article>
      <article className="metric-card"><div className="metric-icon secure">⌾</div><div><span>Security Mode</span><strong className="metric-word">Safe</strong><small>Draft-only content writes</small></div></article>
    </section>
    <div className="dashboard-main-grid">
      <section className="panel"><div className="panel-head"><div><p className="eyebrow">SITES OVERVIEW</p><h2>وضعیت سایت‌ها</h2></div><Link className="text-link" href="/sites">مدیریت سایت‌ها</Link></div>
        <div className="site-list dashboard-sites">{sites.length === 0 ? <div className="empty">هنوز سایتی ثبت نشده است.</div> : sites.slice(0, 6).map((site) => <article className="site-row" key={site.id}><div className={`status-dot ${site.enabled && site.last_check_status === "ok" ? "online" : site.last_check_status === "error" ? "error-dot" : ""}`} /><div className="site-copy"><strong>{site.name}</strong><a href={site.base_url} target="_blank" rel="noreferrer">{site.base_url}</a><small>{site.last_check_message ?? site.username}</small></div><span className={`mini-badge ${site.enabled ? "enabled" : "disabled"}`}>{site.enabled ? "فعال" : "غیرفعال"}</span></article>)}</div>
      </section>
      <section className="panel"><div className="panel-head"><div><p className="eyebrow">RECENT ACTIVITY</p><h2>فعالیت اخیر</h2></div><Link className="text-link" href="/audit">مشاهده همه</Link></div>
        <div className="activity-list">{auditResult.rows.length === 0 ? <div className="empty">فعالیتی ثبت نشده است.</div> : auditResult.rows.map((row) => <div className="activity-item" key={row.id}><span className="activity-mark" /><div><strong>{actionLabels[row.action] ?? row.action}</strong><small>{row.site_name ?? "سیستم"} · {new Date(row.created_at).toLocaleString("fa-IR")}</small></div></div>)}</div>
      </section>
    </div>
    <section className="quick-actions"><Link className="quick-card" href="/content"><span>✦</span><div><strong>مدیریت محتوا</strong><small>مشاهده، جستجو و ویرایش Draftها</small></div><b>←</b></Link><Link className="quick-card" href="/content/new"><span>＋</span><div><strong>پیش‌نویس جدید</strong><small>ایجاد محتوای جدید روی سایت فعال</small></div><b>←</b></Link><Link className="quick-card" href="/sites"><span>◎</span><div><strong>اتصال سایت</strong><small>افزودن یا تست اتصال WordPress</small></div><b>←</b></Link></section>
  </AppShell>;
}
