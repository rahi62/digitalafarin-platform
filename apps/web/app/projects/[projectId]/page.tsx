import Link from "next/link";
import { getProject } from "@/lib/control-plane";
import { lifecycleLabel } from '@/lib/provisioning';
import { newServicePath } from '@/lib/provisioning';
import { OperationRefresh } from '@/components/OperationRefresh';

export const dynamic = "force-dynamic";

function displayState(service: NonNullable<Awaited<ReturnType<typeof getProject>>["services"]>[number]) {
  if (['pending', 'provisioning', 'provision_failed'].includes(service.lifecycle_state)) return { label: lifecycleLabel(service.lifecycle_state), tone: service.lifecycle_state === 'provision_failed' ? 'bad' : 'warn' };
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
            <Link className="railSecondaryButton" href={newServicePath(project.id)}>
              + Add Service
            </Link>
          </div>
        </div>
      </header>

      <section className="railCanvas">
        <OperationRefresh active={services.some(service => ['pending', 'provisioning'].includes(service.lifecycle_state))} />
        <div className="railCanvasGrid" />
        {services.length === 0 && <div className="railEmpty railEmptyCompact">
          <h2>No services yet</h2>
          <p>مخزن Git برنامه‌تان را دیپلوی کنید و نخستین سرویس این پروژه را بسازید.</p>
          <Link className="railPrimaryButton" href={newServicePath(project.id)}>Add Service</Link>
        </div>}
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

          <Link className="railAddServiceCard" href={newServicePath(project.id)}>
            <span>＋</span>
            <strong>Add Service</strong>
            <small>دیپلوی برنامه از مخزن Git</small>
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
