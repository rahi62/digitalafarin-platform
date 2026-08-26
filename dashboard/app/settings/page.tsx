import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { dashboardConfig } from "@/lib/config";
import { db, initializeDatabase } from "@/lib/db";
import { listGscProperties } from "@/lib/gsc";
import { requireAdmin } from "@/lib/session";
import { disconnectGscAction, saveGscPropertyAction, testGscAction } from "./actions";
import "./settings.css";

type ConnectionRow = {
  last_check_status: string | null;
  last_check_message: string | null;
  last_checked_at: Date | null;
  connected_at: Date;
};

type SiteRow = {
  id: string;
  name: string;
  base_url: string;
  enabled: boolean;
  gsc_property_url: string | null;
};

export default async function SettingsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await requireAdmin();
  await initializeDatabase();
  const params = await searchParams;
  const connectionResult = await db.query<ConnectionRow>("SELECT last_check_status,last_check_message,last_checked_at,connected_at FROM gsc_connection WHERE id=1 LIMIT 1");
  const connection = connectionResult.rows[0];
  const sitesResult = await db.query<SiteRow>("SELECT id,name,base_url,enabled,gsc_property_url FROM wordpress_sites ORDER BY name ASC");
  const sites = sitesResult.rows;
  let properties: Awaited<ReturnType<typeof listGscProperties>> = [];
  let propertyError = "";
  if (connection && dashboardConfig.gscOAuthConfigured) {
    try { properties = await listGscProperties(); }
    catch (error) { propertyError = error instanceof Error ? error.message : "دریافت Propertyهای Search Console ناموفق بود."; }
  }

  const connectedMessage = params.gscConnected === "1" ? `اتصال Search Console برقرار شد؛ ${String(params.properties ?? "0")} Property در دسترس است.` : "";
  const oauthError = typeof params.gscError === "string" ? params.gscError : "";

  return <AppShell active="settings" title="تنظیمات و اتصال‌ها" description="اتصال‌های خارجی Agent را از اینجا مدیریت کنید؛ Credentialها در رابط کاربری نمایش داده نمی‌شوند.">
    {(connectedMessage || oauthError) && <div className={oauthError ? "error-banner" : "success notice settings-notice"}>{oauthError || connectedMessage}</div>}

    <div className="two-column-layout settings-layout">
      <section className="panel">
        <div className="panel-head"><div><p className="eyebrow">GOOGLE SEARCH CONSOLE</p><h2>اتصال Search Console</h2></div><span className={`mini-badge ${connection?.last_check_status === "ok" ? "enabled" : "disabled"}`}>{connection ? connection.last_check_status === "ok" ? "متصل" : "نیازمند بررسی" : "متصل نیست"}</span></div>

        {!dashboardConfig.gscOAuthConfigured ? <div className="empty gsc-config-empty">
          <strong>OAuth گوگل هنوز روی سرور تنظیم نشده است.</strong>
          <p>سه متغیر <code>GSC_GOOGLE_CLIENT_ID</code>، <code>GSC_GOOGLE_CLIENT_SECRET</code> و <code>GSC_GOOGLE_REDIRECT_URI</code> را در Environment پنل تنظیم کنید.</p>
        </div> : !connection ? <div className="integration-connect">
          <div><strong>اتصال Read-only به Google Search Console</strong><p>Agent فقط داده‌های Search Console را می‌خواند و هیچ تنظیم یا Property را در حساب گوگل تغییر نمی‌دهد.</p></div>
          <Link className="button-link primary" href="/api/gsc/oauth/start">اتصال حساب Google</Link>
        </div> : <>
          <div className="integration-status-grid">
            <div><span>وضعیت</span><strong>{connection.last_check_status === "ok" ? "سالم" : "نیازمند بررسی"}</strong></div>
            <div><span>Propertyهای در دسترس</span><strong>{propertyError ? "—" : properties.length}</strong></div>
            <div><span>آخرین بررسی</span><strong>{connection.last_checked_at ? new Date(connection.last_checked_at).toLocaleString("fa-IR") : "—"}</strong></div>
          </div>
          {connection.last_check_message && <p className="security-note">{connection.last_check_message}</p>}
          {propertyError && <div className="error-banner"><strong>خطا در GSC</strong><span>{propertyError}</span></div>}
          <div className="site-actions settings-actions"><form action={testGscAction}><button className="secondary" type="submit">تست اتصال</button></form><Link className="button-link secondary" href="/api/gsc/oauth/start">اتصال مجدد</Link><form action={disconnectGscAction}><button className="ghost" type="submit">قطع اتصال</button></form></div>
        </>}
      </section>

      <aside className="panel">
        <div className="panel-head"><div><p className="eyebrow">MCP ACCESS</p><h2>دسترسی ChatGPT</h2></div></div>
        <div className="security-note integration-note"><strong>داده‌های قابل استفاده توسط Agent</strong><p>Performance شامل Clicks، Impressions، CTR و Average Position با ابعاد Query، Page، Device، Country و Date. اتصال با scope فقط‌خواندنی Search Console انجام می‌شود.</p></div>
        <div className="security-note integration-note"><strong>امنیت Token</strong><p>Refresh Token با AES-256-GCM داخل PostgreSQL رمزنگاری می‌شود. MCP فقط از broker داخلی یک Access Token کوتاه‌عمر دریافت می‌کند و Client Secret یا Refresh Token در اختیار ChatGPT قرار نمی‌گیرد.</p></div>
      </aside>
    </div>

    <section className="panel settings-mapping-panel">
      <div className="panel-head"><div><p className="eyebrow">PROPERTY MAPPING</p><h2>اتصال هر سایت به GSC Property</h2></div><span className="count-pill">{sites.filter((site) => site.gsc_property_url).length} متصل</span></div>
      {!connection ? <div className="empty">ابتدا حساب Search Console را متصل کنید.</div> : sites.length === 0 ? <div className="empty">سایتی در پنل ثبت نشده است.</div> : <div className="site-list">{sites.map((site) => <article className="site-card" key={site.id}>
        <div className="site-card-main"><div className={`status-dot ${site.gsc_property_url ? "online" : ""}`} /><div className="site-copy"><strong>{site.name}</strong><a href={site.base_url} target="_blank" rel="noreferrer">{site.base_url}</a><small>{site.gsc_property_url ?? "GSC Property انتخاب نشده"}</small></div></div>
        <form action={saveGscPropertyAction} className="property-map-form"><input type="hidden" name="siteId" value={site.id}/><select name="propertyUrl" defaultValue={site.gsc_property_url ?? ""}><option value="">بدون اتصال</option>{properties.map((property) => <option value={property.siteUrl} key={property.siteUrl}>{property.siteUrl} · {property.permissionLevel}</option>)}</select><button className="secondary small-button" type="submit">ذخیره</button></form>
      </article>)}</div>}
    </section>
  </AppShell>;
}
