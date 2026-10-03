import Link from "next/link";
import { listProjects } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function PlatformSettingsPage() {
  const projects = await listProjects();

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
            <p>GitHub App connection و repository authorization در مرحله Integration تکمیل می‌شود. Auto Deploy برای هر سرویس از Service Settings کنترل می‌شود.</p>
          </div>
        </div>
      </section>
    </main>
  );
}
