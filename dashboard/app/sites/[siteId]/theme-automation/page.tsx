import Link from "next/link";
import { notFound } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { ThemeAutomationForm } from "@/components/theme-automation-form";
import { requireAdmin } from "@/lib/session";
import { getSiteConnection, listSites } from "@/lib/sites";
import {
  getThemeAutomationPolicy,
  getThemeAutomationStatus,
  type ThemeAutomationPolicy,
  type ThemeAutomationStatus,
} from "@/lib/theme-automation";

const DEFAULT_POLICY: ThemeAutomationPolicy = {
  enabled: false,
  fullFileWriteEnabled: false,
  allowedFiles: [],
  allowedDirectories: [],
  maxFileBytes: 1_048_576,
  backupRetentionPerFile: 20,
  autoRollbackOnQaFailure: true,
};

function Gate({ label, ok }: { label: string; ok: boolean }) {
  return <div className={`theme-gate ${ok ? "ready" : "blocked"}`}>
    <span className="status-dot" />
    <strong>{label}</strong>
    <small>{ok ? "آماده" : "در دسترس نیست"}</small>
  </div>;
}

export default async function ThemeAutomationPage({
  params,
}: {
  params: Promise<{ siteId: string }>;
}) {
  await requireAdmin();
  const { siteId } = await params;
  const sites = await listSites(false);
  const site = sites.find((item) => item.id === siteId);
  if (!site) notFound();

  let status: ThemeAutomationStatus | null = null;
  let policy = DEFAULT_POLICY;
  let hardDeniedFiles = ["functions.php", "header.php", "footer.php", "index.php"];
  let maxFileBytes = 2_097_152;
  let maxBackupRetentionPerFile = 50;
  let error: string | null = null;

  if (!site.enabled) {
    error = "این سایت در WP Agent غیرفعال است. برای Theme Automation ابتدا سایت را فعال کنید.";
  } else {
    try {
      const connection = await getSiteConnection(siteId);
      const [statusResult, policyResult] = await Promise.all([
        getThemeAutomationStatus(connection),
        getThemeAutomationPolicy(connection),
      ]);
      status = statusResult;
      policy = policyResult.policy;
      hardDeniedFiles = policyResult.hardDeniedFiles;
      maxFileBytes = policyResult.limits?.maxFileBytes ?? maxFileBytes;
      maxBackupRetentionPerFile = policyResult.limits?.maxBackupRetentionPerFile ?? maxBackupRetentionPerFile;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : "دریافت وضعیت Theme Automation ناموفق بود.";
    }
  }

  return <AppShell
    active="sites"
    title="Theme Automation"
    description={`کنترل امن Templateهای PHP برای ${site.name}`}
  >
    <div className="theme-automation-page">
      <div className="theme-page-nav">
        <Link className="ghost small-button" href="/sites">بازگشت به سایت‌ها</Link>
        <a className="secondary small-button" href={site.base_url} target="_blank" rel="noreferrer">مشاهده سایت</a>
      </div>

      {error && <section className="panel"><p className="error">{error}</p><div className="security-note"><strong>ZIP fallback</strong><p>تا وقتی Bridge Theme Automation قابل تأیید نیست، Agent نباید فایل Production را مستقیم تغییر دهد. فایل ZIP پوسته مسیر امن جایگزین است و SEO Meta از مسیر Page SEO فعلی اعمال می‌شود.</p></div></section>}

      {status && <>
        <section className="panel">
          <div className="panel-head"><div><p className="eyebrow">ACTIVE THEME</p><h2>{status.theme.name || status.theme.stylesheet}</h2></div><span className={`mini-badge ${status.zipFallbackRecommended ? "disabled" : "enabled"}`}>{status.zipFallbackRecommended ? "ZIP fallback" : "Direct write ready"}</span></div>
          <div className="theme-meta-grid">
            <div><small>Stylesheet</small><strong>{status.theme.stylesheet}</strong></div>
            <div><small>Version</small><strong>{status.theme.version || "—"}</strong></div>
            <div><small>نوع قالب</small><strong>{status.theme.childTheme ? "Child Theme" : "Theme"}</strong></div>
            <div><small>Policy</small><strong>{policy.enabled ? "فعال" : "غیرفعال"}</strong></div>
          </div>
          <div className="theme-gates">
            <Gate label="PHP lint" ok={status.capabilities.phpLint} />
            <Gate label="Atomic rename" ok={status.capabilities.atomicRename} />
            <Gate label="Backup" ok={status.capabilities.backup} />
            <Gate label="HTTP QA" ok={status.capabilities.httpQa} />
          </div>
        </section>

        <section className="panel">
          <div className="panel-head"><div><p className="eyebrow">WRITE POLICY</p><h2>Allowlist و Safety Policy</h2></div></div>
          <ThemeAutomationForm
            siteId={siteId}
            policy={policy}
            hardDeniedFiles={hardDeniedFiles}
            maxFileBytes={maxFileBytes}
            maxBackupRetentionPerFile={maxBackupRetentionPerFile}
          />
        </section>

        <section className="panel">
          <div className="panel-head"><div><p className="eyebrow">AGENT FLOW</p><h2>مسیر مجاز تغییر پیلار</h2></div></div>
          <div className="security-note">
            <p><strong>Resolve → Read → Preview → Hash/Lint → Backup → Atomic Write → HTTP QA → Rollback در صورت خطا</strong></p>
            <p>Agent هیچ ابزار تغییر Policy، Shell یا فایل عمومی WordPress ندارد. SEO Title/Meta/Canonical/Noindex نیز همچنان از ابزارهای Page SEO مستقل مدیریت می‌شوند.</p>
          </div>
        </section>
      </>}
    </div>
  </AppShell>;
}
