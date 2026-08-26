import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { db, initializeDatabase } from "@/lib/db";
import { requireAdmin } from "@/lib/session";
import { listSites } from "@/lib/sites";

type AuditRow = { id: string; action: string; created_at: Date; site_name: string | null; details: Record<string, unknown> };

const actionLabels: Record<string, string> = {
  "site.created": "سایت جدید اضافه شد",
  "site.toggled": "وضعیت سایت تغییر کرد",
  "site.health_checked": "اتصال سایت بررسی شد",
  "agent.site_resolved": "عامل به وردپرس دسترسی گرفت",
  "agent.gsc_resolved": "عامل به Search Console دسترسی گرفت",
  "content.draft_created": "پیش‌نویس جدید ساخته شد",
  "content.draft_updated": "پیش‌نویس ویرایش شد",
  "content.post_updated": "نوشته منتشرشده ویرایش شد",
  "content.published": "پیش‌نویس منتشر شد",
  "gsc.oauth_config_updated": "تنظیمات Google OAuth تغییر کرد",
  "gsc.oauth_config_removed": "تنظیمات Google OAuth حذف شد",
  "gsc.connected": "Search Console متصل شد",
  "gsc.disconnected": "اتصال Search Console قطع شد",
  "gsc.property_mapped": "GSC Property سایت تغییر کرد",
};

export default async function DashboardPage() {
  await requireAdmin();
  await initializeDatabase();

  const sites = await listSites(false);
  const enabled = sites.filter((site) => site.enabled).length;
  const healthy = sites.filter((site) => site.enabled && site.last_check_status === "ok").length;
  const auditResult = await db.query<AuditRow>(`SELECT a.id::text,a.action,a.created_at,a.details,s.name AS site_name FROM audit_logs a LEFT JOIN wordpress_sites s ON s.id=a.site_id ORDER BY a.created_at DESC LIMIT 6`);
  const agentOps = await db.query<{ count: string }>("SELECT COUNT(*)::text AS count FROM audit_logs WHERE action IN ('agent.site_resolved','agent.gsc_resolved') AND created_at >= NOW() - INTERVAL '24 hours'");
  const gsc = await db.query<{ last_check_status: string | null }>("SELECT last_check_status FROM gsc_connection WHERE id=1 LIMIT 1");
  const gscMapped = await db.query<{ count: string }>("SELECT COUNT(*)::text AS count FROM wordpress_sites WHERE enabled=TRUE AND gsc_property_url IS NOT NULL AND gsc_property_url <> ''");
  const gscHealthy = gsc.rows[0]?.last_check_status === "ok";

  return <AppShell active="dashboard" title="داشبورد" description="مرکز کنترل WordPress، Search Console، محتوا و فعالیت عامل هوشمند.">
    <section className="metric-grid">
      <article className="metric-card">
        <div className="metric-icon">◎</div>
        <div><span>سایت‌های ثبت‌شده</span><strong>{sites.length}</strong><small>{enabled} سایت فعال</small></div>
      </article>
      <article className="metric-card">
        <div className="metric-icon healthy">✓</div>
        <div><span>اتصال WordPress</span><strong>{healthy}</strong><small>از {enabled} اتصال فعال</small></div>
      </article>
      <article className="metric-card">
        <div className="metric-icon agent">G</div>
        <div><span>Google Search Console</span><strong className="metric-word">{gscHealthy ? "متصل" : "—"}</strong><small>{gscMapped.rows[0]?.count ?? "0"} سایت دارای Property</small></div>
      </article>
      <article className="metric-card security-metric">
        <div className="metric-icon secure">✦</div>
        <div><span>دسترسی عامل در ۲۴ ساعت</span><strong>{agentOps.rows[0]?.count ?? "0"}</strong><small>WordPress + GSC · ثبت‌شده در Audit</small></div>
      </article>
    </section>

    <div className="dashboard-main-grid">
      <section className="panel dashboard-panel">
        <div className="panel-head">
          <div><p className="eyebrow">SITES OVERVIEW</p><h2>وضعیت سایت‌ها</h2></div>
          <Link className="text-link" href="/sites">مدیریت سایت‌ها</Link>
        </div>
        <div className="site-list dashboard-sites">
          {sites.length === 0 ? <div className="empty">هنوز سایتی ثبت نشده است.</div> : sites.slice(0, 6).map((site) =>
            <article className="site-row" key={site.id}>
              <div className={`status-dot ${site.enabled && site.last_check_status === "ok" ? "online" : site.last_check_status === "error" ? "error-dot" : ""}`} />
              <div className="site-copy"><strong>{site.name}</strong><a href={site.base_url} target="_blank" rel="noreferrer">{site.base_url}</a><small>{site.last_check_message ?? site.username}</small></div>
              <span className={`mini-badge ${site.enabled ? "enabled" : "disabled"}`}>{site.enabled ? "فعال" : "غیرفعال"}</span>
            </article>
          )}
        </div>
      </section>

      <section className="panel dashboard-panel">
        <div className="panel-head">
          <div><p className="eyebrow">RECENT ACTIVITY</p><h2>فعالیت‌های اخیر</h2></div>
          <Link className="text-link" href="/audit">مشاهده همه</Link>
        </div>
        <div className="activity-list">
          {auditResult.rows.length === 0 ? <div className="empty">فعالیتی ثبت نشده است.</div> : auditResult.rows.map((row) =>
            <div className="activity-item" key={row.id}>
              <span className="activity-mark" />
              <div><strong>{actionLabels[row.action] ?? row.action}</strong><small>{row.site_name ?? "سیستم"}<span>•</span>{new Date(row.created_at).toLocaleString("fa-IR")}</small></div>
            </div>
          )}
        </div>
      </section>
    </div>

    <section className="quick-section">
      <div className="section-heading"><div><p className="eyebrow">QUICK ACTIONS</p><h2>دسترسی سریع</h2></div><p>Agent می‌تواند Draft بسازد، منتشر کند و با درخواست صریح، محتوای زنده را به‌روزرسانی کند.</p></div>
      <div className="quick-actions">
        <Link className="quick-card" href="/content"><span>✦</span><div><strong>مدیریت محتوا</strong><small>Draft و نوشته‌های منتشرشده</small></div><b>←</b></Link>
        <Link className="quick-card" href="/content/new"><span>＋</span><div><strong>نوشته جدید</strong><small>ساخت Draft و انتشار بعد از تکمیل</small></div><b>←</b></Link>
        <Link className="quick-card" href="/settings"><span>G</span><div><strong>Search Console</strong><small>تنظیم OAuth، اتصال حساب و Propertyها از پنل</small></div><b>←</b></Link>
      </div>
    </section>
  </AppShell>;
}
