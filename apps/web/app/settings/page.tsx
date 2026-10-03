import Link from "next/link";
import { getGitHubIntegration, listProjects } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function PlatformSettingsPage() {
  const [projects, github] = await Promise.all([listProjects(), getGitHubIntegration()]);

  return (
    <main className="railPage">
      <header className="railProjectHeader">
        <div>
          <p className="railEyebrow">PLATFORM SETTINGS</p>
          <h1>Settings</h1>
          <p>مدیریت پروژه‌ها، تنظیمات سرویس‌ها و Integrationهای پلتفرم</p>
        </div>
      </header>

      <section className="railServiceSection">
        <div className="railSectionHeader">
          <div>
            <h2>Projects & Services</h2>
            <p>برای ویرایش یا حذف، پروژه را باز کنید. حذف پروژه فقط بعد از حذف منابع وابسته مجاز است.</p>
          </div>
        </div>
        <div className="railDeploymentList">
          {projects.length === 0 ? (
            <div className="railEmpty railEmptyCompact">
              <h3>No projects</h3>
              <p>هنوز پروژه‌ای در Control Plane ثبت نشده است.</p>
            </div>
          ) : projects.map((project) => (
            <div className="railDeploymentRow" key={project.id}>
              <div>
                <strong>{project.name}</strong>
                <small dir="ltr">{project.slug}</small>
              </div>
              <Link className="railSecondaryButton" href={`/projects/${project.id}/settings`}>Project settings</Link>
              <Link className="railSecondaryButton" href={`/projects/${project.id}`}>Services</Link>
            </div>
          ))}
        </div>
      </section>

      <section className="railServiceSection">
        <div className="railSectionHeader">
          <div>
            <h2>GitHub</h2>
            <p>GitHub App دسترسی repository را با installation token کوتاه‌عمر فراهم می‌کند؛ هیچ GitHub token دائمی روی VPS ذخیره نمی‌شود.</p>
          </div>
          {github.configured && <a className="railPrimaryButton" href={github.install_url}>Connect GitHub</a>}
        </div>
        {!github.configured ? (
          <div className="railEmpty railEmptyCompact">
            <h3>GitHub App configuration required</h3>
            <p>GITHUB_APP_ID، GITHUB_APP_PRIVATE_KEY، GITHUB_APP_WEBHOOK_SECRET و GITHUB_APP_SLUG باید در API production تنظیم شوند.</p>
          </div>
        ) : github.installations.length === 0 ? (
          <div className="railEmpty railEmptyCompact"><h3>Not connected</h3><p>برای انتخاب repository ابتدا GitHub App را نصب کنید.</p></div>
        ) : (
          <div className="railDeploymentList">
            {github.installations.map((installation) => (
              <div className="railDeploymentRow" key={installation.installation_id}>
                <div>
                  <strong>{installation.account_login}</strong>
                  <small>{installation.account_type} · {installation.repository_selection}</small>
                </div>
                <span className={installation.suspended ? "railFormError" : "railFormSuccess"}>{installation.suspended ? "Suspended" : "Connected"}</span>
                <Link className="railSecondaryButton" href={`/settings/github/${installation.installation_id}`}>Repositories</Link>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
