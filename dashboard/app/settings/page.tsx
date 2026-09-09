import { headers } from "next/headers";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { GscOAuthLink } from "@/components/gsc-oauth-link";
import { GscOAuthConfigForm } from "@/components/gsc-oauth-config-form";
import { db, initializeDatabase } from "@/lib/db";
import { listGscProperties } from "@/lib/gsc";
import { getGscOAuthAppStatus } from "@/lib/integration-settings";
import { gscCallbackUrl, resolvePublicOrigin } from "@/lib/public-origin";
import { requireAdmin } from "@/lib/session";
import { clearGscOAuthConfigAction, disconnectGscAction, saveGscPropertyAction, testGscAction } from "./actions";
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
  const requestHeaders = await headers();
  const callbackUrl = gscCallbackUrl(resolvePublicOrigin(requestHeaders));
  const oauthApp = await getGscOAuthAppStatus();
  const connectionResult = await db.query<ConnectionRow>("SELECT last_check_status,last_check_message,last_checked_at,connected_at FROM gsc_connection WHERE id=1 LIMIT 1");
  const connection = connectionResult.rows[0];
  const sitesResult = await db.query<SiteRow>("SELECT id,name,base_url,enabled,gsc_property_url FROM wordpress_sites ORDER BY name ASC");
  const sites = sitesResult.rows;
  let properties: Awaited<ReturnType<typeof listGscProperties>> = [];
  let propertyError = "";
  if (connection && oauthApp.configured) {
    try { properties = await listGscProperties(); }
    catch (error) { propertyError = error instanceof Error ? error.message : "دریافت Propertyهای Search Console ناموفق بود."; }
  }

  const connectedMessage = params.gscConnected === "1" ? `اتصال Search Console برقرار شد؛ ${String(params.properties ?? "0")} Property در دسترس است.` : "";
  const oauthError = typeof params.gscError === "string" ? params.gscError : "";

  return <AppShell active="settings" title="تنظیمات و اتصال‌ها" description="Integrationها را از خود پنل مدیریت کنید؛ Environment فقط برای secretهای زیرساختی باقی می‌ماند.">
    {(connectedMessage || oauthError) && <div className={oauthError ? "error-banner" : "success notice settings-notice"}>{oauthError || connectedMessage}</div>}

    <div className="two-column-layout settings-layout">
      <section className="panel">
        <div className="panel-head">
          <div><p className="eyebrow">GOOGLE OAUTH APP</p><h2>تنظیمات OAuth پلتفرم</h2></div>
          <span className={`mini-badge ${oauthApp.configured ? "enabled" : "disabled"}`}>{oauthApp.configured ? "پیکربندی شده" : "نیازمند تنظیم"}</span>
        </div>
        <p className="settings-copy">در نسخه Hosted/SaaS این بخش یک‌بار توسط مدیر پلتفرم تنظیم می‌شود و مشتری فقط حساب Google خود را Connect می‌کند. در نسخه White-label یا Self-hosted مدیر همان نصب می‌تواند Client خودش را وارد کند.</p>
        <GscOAuthConfigForm clientId={oauthApp.clientId} hasClientSecret={oauthApp.hasClientSecret} callbackUrl={callbackUrl} />
        {oauthApp.configured && <form action={clearGscOAuthConfigAction} className="danger-zone"><div><strong>حذف تنظیمات OAuth</strong><small>اتصال GSC و mapping سایت‌ها نیز پاک می‌شود؛ داده WordPress حذف نمی‌شود.</small></div><button className="ghost" type="submit">حذف تنظیمات</button></form>}
      </section>

      <aside className="panel">
        <div className="panel-head"><div><p className="eyebrow">PRODUCT MODEL</p><h2>مدل قابل فروش</h2></div></div>
        <div className="security-note integration-note"><strong>Hosted SaaS</strong><p>DigitalAfarin یک OAuth App مرکزی دارد. Client Secret فقط یک‌بار در پنل مدیر سیستم ثبت می‌شود و کاربران نهایی هیچ Secretای وارد نمی‌کنند.</p></div>
        <div className="security-note integration-note"><strong>White-label / Self-hosted</strong><p>هر نصب می‌تواند OAuth Client اختصاصی خودش را از همین پنل ثبت کند. Callback بر اساس دامنه واقعی همان پنل تولید می‌شود و در کد hard-code نیست.</p></div>
        <div className="security-note integration-note"><strong>امنیت</strong><p>Client Secret و Refresh Token هر دو با AES-256-GCM رمزنگاری می‌شوند. MCP فقط Access Token کوتاه‌عمر دریافت می‌کند.</p></div>
      </aside>
    </div>

    <div className="two-column-layout settings-layout">
      <section className="panel">
        <div className="panel-head"><div><p className="eyebrow">GOOGLE SEARCH CONSOLE</p><h2>اتصال حساب Search Console</h2></div><span className={`mini-badge ${connection?.last_check_status === "ok" ? "enabled" : "disabled"}`}>{connection ? connection.last_check_status === "ok" ? "متصل" : "نیازمند بررسی" : "متصل نیست"}</span></div>

        {!oauthApp.configured ? <div className="empty gsc-config-empty"><strong>ابتدا Google OAuth App را در همین صفحه ثبت کنید.</strong><p>پس از ذخیره Client ID و Client Secret، دکمه اتصال حساب Google فعال می‌شود.</p></div> : !connection ? <div className="integration-connect">
          <div><strong>اتصال Read-only به Google Search Console</strong><p>Agent فقط داده‌های Search Console را می‌خواند و هیچ Property یا تنظیمی را در حساب Google تغییر نمی‌دهد.</p></div>
          <GscOAuthLink className="button-link primary" label="اتصال حساب Google" />
        </div> : <>
          <div className="integration-status-grid">
            <div><span>وضعیت</span><strong>{connection.last_check_status === "ok" ? "سالم" : "نیازمند بررسی"}</strong></div>
            <div><span>Propertyهای در دسترس</span><strong>{propertyError ? "—" : properties.length}</strong></div>
            <div><span>آخرین بررسی</span><strong>{connection.last_checked_at ? new Date(connection.last_checked_at).toLocaleString("fa-IR") : "—"}</strong></div>
          </div>
          {connection.last_check_message && <p className="security-note">{connection.last_check_message}</p>}
          {propertyError && <div className="error-banner"><strong>خطا در GSC</strong><span>{propertyError}</span></div>}
          <div className="site-actions settings-actions"><form action={testGscAction}><button className="secondary" type="submit">تست اتصال</button></form><GscOAuthLink className="button-link secondary" label="اتصال مجدد" /><form action={disconnectGscAction}><button className="ghost" type="submit">قطع اتصال</button></form></div>
        </>}
      </section>

      <aside className="panel">
        <div className="panel-head"><div><p className="eyebrow">MCP ACCESS</p><h2>دسترسی ChatGPT</h2></div></div>
        <div className="security-note integration-note"><strong>Performance</strong><p>Clicks، Impressions، CTR و Average Position با Query، Page، Device، Country، Date و فیلترهای قابل ترکیب.</p></div>
        <div className="security-note integration-note"><strong>Indexing & Sitemaps</strong><p>URL Inspection برای وضعیت نسخه موجود در Google Index و خواندن Sitemapها نیز در اختیار MCP است. همه ابزارهای GSC فقط‌خواندنی هستند.</p></div>
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
