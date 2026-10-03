import Link from "next/link";
import { ProjectSettingsForm, ServiceSettingsForm } from "@/components/SettingsForms";
import {
  getGitHubIntegration,
  getProject,
  listGitHubRepositories,
  listProjects,
} from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function PlatformSettingsPage() {
  const [summaries, github] = await Promise.all([listProjects(), getGitHubIntegration()]);
  const projects = await Promise.all(summaries.map((project) => getProject(project.id)));
  const repositories = (
    await Promise.all(
      github.installations
        .filter((installation) => !installation.suspended)
        .map((installation) =>
          listGitHubRepositories(installation.installation_id).catch(() => []),
        ),
    )
  ).flat();

  return (
    <main className="railPage">
      <header className="railProjectHeader">
        <div>
          <p className="railEyebrow">PLATFORM SETTINGS</p>
          <h1>Settings</h1>
          <p>ویرایش مستقیم پروژه‌ها، سرویس‌ها، deployment configuration و Integrationهای پلتفرم</p>
        </div>
      </header>

      <section className="railServiceSection">
        <div className="railSectionHeader">
          <div>
            <h2>Projects & Services</h2>
            <p>تنظیمات این بخش مستقیماً قابل ویرایش هستند؛ برای Edit نیازی به خروج از Settings نیست.</p>
          </div>
        </div>
        {projects.length === 0 ? (
          <div className="railEmpty railEmptyCompact">
            <h3>No projects</h3>
            <p>هنوز پروژه‌ای در Control Plane ثبت نشده است.</p>
          </div>
        ) : projects.map((project) => (
          <div key={project.id}>
            <div className="railSectionHeader">
              <div>
                <h2>{project.name}</h2>
                <p dir="ltr">{project.slug}</p>
              </div>
              <Link className="railSecondaryButton" href={`/projects/${project.id}`}>Open project</Link>
            </div>

            <ProjectSettingsForm project={project} />

            {(project.services ?? []).map((service) => (
              <div key={service.id}>
                <div className="railSectionHeader">
                  <div>
                    <h2>Service · {service.name}</h2>
                    <p dir="ltr">{service.unit_name}</p>
                  </div>
                  <Link
                    className="railSecondaryButton"
                    href={`/projects/${project.id}/services/${service.id}?tab=settings`}
                  >
                    Open service
                  </Link>
                </div>
                <ServiceSettingsForm
                  project={project}
                  service={service}
                  githubRepositories={repositories}
                />
              </div>
            ))}
          </div>
        ))}
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
