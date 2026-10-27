import Link from "next/link";
import { AddSiteForm } from "@/components/add-site-form";
import { AppShell } from "@/components/app-shell";
import { checkSiteAction, toggleSiteAction } from "@/app/actions";
import { requireAdmin } from "@/lib/session";
import { listSites } from "@/lib/sites";

export default async function SitesPage() {
  await requireAdmin();
  const sites = await listSites(false);
  return <AppShell active="sites" title="مدیریت سایت‌ها" description="اتصال‌های مجاز Agent را مدیریت و سلامت REST API هر سایت را بررسی کنید.">
    <div className="two-column-layout">
      <section className="panel"><div className="panel-head"><div><p className="eyebrow">CONNECTED SITES</p><h2>سایت‌های وردپرسی</h2></div><span className="count-pill">{sites.length} سایت</span></div>
        <div className="site-list">{sites.length === 0 ? <div className="empty">هنوز سایتی اضافه نشده است.</div> : sites.map((site) => <article className="site-card" key={site.id}>
          <div className="site-card-main"><div className={`status-dot ${site.enabled && site.last_check_status === "ok" ? "online" : site.last_check_status === "error" ? "error-dot" : ""}`} /><div className="site-copy"><div className="site-title-line"><strong>{site.name}</strong><span className={`mini-badge ${site.enabled ? "enabled" : "disabled"}`}>{site.enabled ? "فعال" : "غیرفعال"}</span></div><a href={site.base_url} target="_blank" rel="noreferrer">{site.base_url}</a><small>{site.username} · {site.last_check_message ?? "هنوز بررسی نشده"}</small>{site.last_checked_at && <small>آخرین بررسی: {new Date(site.last_checked_at).toLocaleString("fa-IR")}</small>}</div></div>
          <div className="site-actions"><Link className="secondary small-button" href={`/sites/${site.id}/theme-automation`}>Theme Automation</Link><form action={checkSiteAction}><input type="hidden" name="id" value={site.id}/><button className="secondary small-button" type="submit">تست اتصال</button></form><form action={toggleSiteAction}><input type="hidden" name="id" value={site.id}/><button className="ghost small-button" type="submit">{site.enabled ? "غیرفعال‌سازی" : "فعال‌سازی"}</button></form></div>
        </article>)}</div>
      </section>
      <aside className="panel sticky-panel"><div className="panel-head"><div><p className="eyebrow">NEW CONNECTION</p><h2>افزودن سایت</h2></div></div><AddSiteForm/><div className="security-note"><strong>ذخیره امن Credential</strong><p>Application Password فقط هنگام ثبت دریافت می‌شود، با AES-256-GCM رمزنگاری می‌شود و بعداً در رابط کاربری نمایش داده نمی‌شود.</p></div></aside>
    </div>
  </AppShell>;
}
