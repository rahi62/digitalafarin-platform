import Link from "next/link";
import { getProject, listProjects } from "@/lib/control-plane";
import { createProjectAction } from "./actions";

export const dynamic = "force-dynamic";

function serviceState(services: NonNullable<Awaited<ReturnType<typeof getProject>>["services"]>) {
  if (services.some((service) => service.active_state === "failed")) return "Degraded";
  if (services.some((service) => service.active_state === "active")) return "Running";
  if (services.length === 0) return "Empty";
  return "Configured";
}

export default async function ProjectsPage() {
  const summaries = await listProjects();
  const projects = await Promise.all(summaries.map((project) => getProject(project.id)));

  return (
    <main className="railPage">
      <header className="railPageHeader">
        <div>
          <p className="railEyebrow">WORKSPACE</p>
          <h1>Projects</h1>
          <p>پروژه‌ها، سرویس‌ها و استقرارها؛ بدون درگیر شدن با جزئیات زیرساخت.</p>
        </div>

        <details className="railNewProject">
          <summary>+ New Project</summary>
          <form action={createProjectAction} className="railCreateForm">
            <label>
              <span>نام پروژه</span>
              <input name="name" required maxLength={120} placeholder="NOVA" />
            </label>
            <label>
              <span>Slug</span>
              <input
                name="slug"
                required
                maxLength={80}
                pattern="[a-z0-9]+(?:[-_][a-z0-9]+)*"
                placeholder="nova"
                dir="ltr"
              />
            </label>
            <button type="submit">Create Project</button>
          </form>
        </details>
      </header>

      {projects.length === 0 ? (
        <section className="railEmpty">
          <div className="railEmptyIcon">＋</div>
          <h2>اولین پروژه را بساز</h2>
          <p>بعد از ساخت Project، سرویس‌ها را از Repository یا سرویس‌های موجود به آن متصل می‌کنیم.</p>
        </section>
      ) : (
        <section className="railProjectGrid">
          {projects.map((project) => {
            const services = project.services ?? [];
            const state = serviceState(services);
            const managed = services.filter((service) => service.lifecycle_state === "managed").length;
            return (
              <Link href={`/projects/${project.id}`} className="railProjectCard" key={project.id}>
                <div className="railProjectTop">
                  <span className="railProjectIcon">{project.name.slice(0, 1).toUpperCase()}</span>
                  <span className={`railState railState${state}`}>{state}</span>
                </div>
                <div>
                  <h2>{project.name}</h2>
                  <code dir="ltr">{project.slug}</code>
                </div>
                <div className="railProjectMeta">
                  <span>{services.length} services</span>
                  <span>{managed} managed</span>
                </div>
              </Link>
            );
          })}
        </section>
      )}
    </main>
  );
}
