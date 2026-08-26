import { AppShell } from "@/components/app-shell";
import { db, initializeDatabase } from "@/lib/db";
import { requireAdmin } from "@/lib/session";

type AuditRow = { id: string; site_id: string | null; action: string; details: Record<string, unknown>; created_at: Date; site_name: string | null };

const actionLabels: Record<string, string> = {
  "site.created": "افزودن سایت",
  "site.toggled": "تغییر وضعیت سایت",
  "site.health_checked": "بررسی اتصال",
  "agent.site_resolved": "دسترسی Agent",
  "content.draft_created": "ایجاد پیش‌نویس",
  "content.draft_updated": "ویرایش پیش‌نویس",
};

function detailText(details: Record<string, unknown>) {
  const pieces: string[] = [];
  if (details.postId) pieces.push(`Post #${String(details.postId)}`);
  if (details.title) pieces.push(String(details.title));
  if (details.operation) pieces.push(String(details.operation));
  if (details.status) pieces.push(`status: ${String(details.status)}`);
  return pieces.join(" · ") || "—";
}

export default async function AuditPage() {
  await requireAdmin(); await initializeDatabase();
  const result = await db.query<AuditRow>(`SELECT a.id::text,a.site_id,a.action,a.details,a.created_at,s.name AS site_name FROM audit_logs a LEFT JOIN wordpress_sites s ON s.id=a.site_id ORDER BY a.created_at DESC LIMIT 100`);
  return <AppShell active="audit" title="گزارش فعالیت" description="ردپای عملیاتی پنل و Agent برای کنترل، عیب‌یابی و امنیت.">
    <section className="panel content-panel"><div className="panel-head"><div><p className="eyebrow">AUDIT TRAIL</p><h2>۱۰۰ رویداد اخیر</h2></div><span className="count-pill">{result.rows.length} رویداد</span></div>
      {result.rows.length === 0 ? <div className="empty">هنوز رویدادی ثبت نشده است.</div> : <div className="content-table-wrap"><table className="content-table audit-table"><thead><tr><th>رویداد</th><th>سایت</th><th>جزئیات</th><th>زمان</th></tr></thead><tbody>{result.rows.map((row) => <tr key={row.id}><td><span className="audit-action">{actionLabels[row.action] ?? row.action}</span><small className="audit-code">{row.action}</small></td><td>{row.site_name ?? "سیستم"}</td><td className="detail-cell">{detailText(row.details ?? {})}</td><td className="date-cell">{new Date(row.created_at).toLocaleString("fa-IR")}</td></tr>)}</tbody></table></div>}
    </section>
  </AppShell>;
}
