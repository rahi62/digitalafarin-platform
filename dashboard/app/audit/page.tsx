import { AppShell } from "@/components/app-shell";
import { db, initializeDatabase } from "@/lib/db";
import { requireAdmin } from "@/lib/session";

type AuditRow = { id: string; site_id: string | null; action: string; details: Record<string, unknown>; created_at: Date; site_name: string | null };

const actionLabels: Record<string, string> = {
  "site.created": "افزودن سایت",
  "site.toggled": "تغییر وضعیت سایت",
  "site.health_checked": "بررسی اتصال WordPress",
  "agent.site_resolved": "دسترسی Agent به WordPress",
  "agent.gsc_resolved": "دسترسی Agent به GSC",
  "content.draft_created": "ایجاد پیش‌نویس",
  "content.draft_updated": "ویرایش پیش‌نویس",
  "content.post_updated": "ویرایش نوشته منتشرشده",
  "content.published": "انتشار پیش‌نویس",
  "content.page_draft_created": "ایجاد پیش‌نویس برگه",
  "content.page_draft_updated": "ویرایش پیش‌نویس برگه",
  "content.page_updated": "ویرایش برگه منتشرشده",
  "content.page_published": "انتشار برگه",
  "content.trashed": "انتقال نوشته به Trash",
  "content.permanently_deleted": "حذف دائمی نوشته",
  "indexing.noindex_updated": "تغییر Noindex",
  "redirect.created": "ساخت Redirect 301",
  "redirect.deleted": "حذف Redirect",
  "gsc.oauth_config_updated": "تغییر تنظیمات Google OAuth",
  "gsc.oauth_config_removed": "حذف تنظیمات Google OAuth",
  "gsc.connected": "اتصال Search Console",
  "gsc.disconnected": "قطع Search Console",
  "gsc.health_checked": "بررسی اتصال Search Console",
  "gsc.property_mapped": "اتصال GSC Property",
};

function detailText(details: Record<string, unknown>) {
  const pieces: string[] = [];
  if (details.postId) pieces.push(`Post #${String(details.postId)}`);
  if (details.pageId) pieces.push(`Page #${String(details.pageId)}`);
  if (details.title) pieces.push(String(details.title));
  if (details.operation) pieces.push(String(details.operation));
  if (details.propertyUrl) pieces.push(String(details.propertyUrl));
  if (details.source) pieces.push(String(details.source));
  if (details.target) pieces.push(`→ ${String(details.target)}`);
  if (details.noindex !== undefined) pieces.push(`noindex: ${String(details.noindex)}`);
  if (details.status) pieces.push(`status: ${String(details.status)}`);
  if (details.properties) pieces.push(`${String(details.properties)} properties`);
  if (details.connectionReset) pieces.push("GSC connection reset");
  if (details.clientIdChanged) pieces.push("Client ID changed");
  if (details.secretChanged) pieces.push("Client Secret changed");
  return pieces.join(" · ") || "—";
}

export default async function AuditPage() {
  await requireAdmin(); await initializeDatabase();
  const result = await db.query<AuditRow>(`SELECT a.id::text,a.site_id,a.action,a.details,a.created_at,s.name AS site_name FROM audit_logs a LEFT JOIN wordpress_sites s ON s.id=a.site_id ORDER BY a.created_at DESC LIMIT 100`);
  return <AppShell active="audit" title="گزارش فعالیت" description="ردپای عملیاتی WordPress، Search Console، پنل و Agent برای کنترل و عیب‌یابی.">
    <section className="panel content-panel"><div className="panel-head"><div><p className="eyebrow">AUDIT TRAIL</p><h2>۱۰۰ رویداد اخیر</h2></div><span className="count-pill">{result.rows.length} رویداد</span></div>
      {result.rows.length === 0 ? <div className="empty">هنوز رویدادی ثبت نشده است.</div> : <div className="content-table-wrap"><table className="content-table audit-table"><thead><tr><th>رویداد</th><th>سایت</th><th>جزئیات</th><th>زمان</th></tr></thead><tbody>{result.rows.map((row) => <tr key={row.id}><td><span className="audit-action">{actionLabels[row.action] ?? row.action}</span><small className="audit-code">{row.action}</small></td><td>{row.site_name ?? "سیستم"}</td><td className="detail-cell">{detailText(row.details ?? {})}</td><td className="date-cell">{new Date(row.created_at).toLocaleString("fa-IR")}</td></tr>)}</tbody></table></div>}
    </section>
  </AppShell>;
}
