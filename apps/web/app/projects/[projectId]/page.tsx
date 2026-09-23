import Link from "next/link";
import { getProject } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

function displayState(service: NonNullable<Awaited<ReturnType<typeof getProject>>["services"]>[number]) {
  if (service.inventory_status === "missing") return { label: "Missing", tone: "muted" };
  if (service.active_state === "active") return { label: "Running", tone: "good" };
  if (service.active_state === "failed") return { label: "Failed", tone: "bad" };
  if (service.lifecycle_state === "managed") return { label: "Managed", tone: "good" };
  return { label: "Needs setup", tone: "warn" };
}

export default async function ProjectPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  const project = await getProject(projectId);
  const services = project.services ?? [];

  return (
    <main className="railPage railCanvasPage">
      <header className="railProjectHeader">
        <div className="railBreadcrumb">
          <Link href="/projects">Projects</Link><span>/</span><strong>{project.name}</strong>
        </div>
        <div className="railProjectTitleRow">
          <div>
            <h1>{project.name}</h1>
            <p><code dir="ltr">{project.slug}</code></p>
          </div>
          <div className="railHeaderActions">
            <span className="railEnvironment"><i /> Production</span>
            <Link className="railSecondaryButton" href={`/migration?project=${encodeURIComponent(project.id)}`}>
              + Add Service
            </Link>
          </div>
        </div>
      </header>

      <section className="railCanvas">
        <div className="railCanvasGrid" />
        <div className="railServiceGrid">
          {services.map((service) => {
            const state = displayState(service);
            return (
              <Link
                href={`/projects/${project.id}/services/${service.id}`}
                className="railServiceCard"
                key={service.id}
              >
                <div className="railServiceHead">
                  <div className="railServiceIdentity">
                    <span className="railServiceIcon">◆</span>
                    <div>
                      <h2>{service.name}</h2>
                      <code dir="ltr">{service.unit_name}</code>
                    </div>
                  </div>
                  <span className={`railServiceStatus railTone-${state.tone}`}>
                    <i /> {state.label}
                  </span>
                </div>

                <div className="railServiceInfo">
                  <span>{service.runtime ?? "Runtime not set"}</span>
                  <span>{service.service_port ? `:${service.service_port}` : "No port"}</span>
                </div>

                <div className="railServiceRepo" dir="ltr">
                  {service.repository ?? "Repository not configured"}
                </div>
              </Link>
            );
          })}

          <Link className="railAddServiceCard" href={`/migration?project=${encodeURIComponent(project.id)}`}>
            <span>＋</span>
            <strong>Add Service</strong>
            <small>Repository or existing systemd service</small>
          </Link>
        </div>
      </section>

      <section className="railResourceStrip">
        <div><strong>{project.variables?.length ?? 0}</strong><span>Variables</span></div>
        <div><strong>{project.domains?.length ?? 0}</strong><span>Domains</span></div>
        <div><strong>{project.volumes?.length ?? 0}</strong><span>Volumes</span></div>
        <div><strong>{project.databases?.length ?? 0}</strong><span>Databases</span></div>
        <Link href="/servers">Infrastructure →</Link>
      </section>
    </main>
  );
}
