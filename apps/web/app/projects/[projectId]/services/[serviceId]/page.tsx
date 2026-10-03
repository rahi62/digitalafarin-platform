import Link from "next/link";
import { deployAction } from "@/app/deployments/actions";
import { getProject, listDeployments } from "@/lib/control-plane";
import { ServiceSettingsForm } from "@/components/SettingsForms";

export const dynamic = "force-dynamic";

const tabs = [
  ["deployments", "Deployments"],
  ["variables", "Variables"],
  ["logs", "Logs"],
  ["settings", "Settings"],
] as const;

function shortCommit(value: string) {
  return value ? value.slice(0, 7) : "—";
}

export default async function ProjectServicePage({
  params,
  searchParams,
}: {
  params: Promise<{ projectId: string; serviceId: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { projectId, serviceId } = await params;
  const query = await searchParams;
  const project = await getProject(projectId);
  const service = (project.services ?? []).find((item) => item.id === serviceId);

  if (!service) {
    return (
      <main className="railPage">
        <h1>Service not found</h1>
        <Link href={`/projects/${projectId}`}>Back to project</Link>
      </main>
    );
  }

  const tab = tabs.some(([key]) => key === query.tab) ? query.tab! : "deployments";
  const deployments = tab === "deployments" ? await listDeployments(service.id) : [];

  return (
    <main className="railPage">
      <header className="railServicePageHeader">
        <div className="railBreadcrumb">
          <Link href="/projects">Projects</Link><span>/</span>
          <Link href={`/projects/${project.id}`}>{project.name}</Link><span>/</span>
          <strong>{service.name}</strong>
        </div>

        <div className="railProjectTitleRow">
          <div>
            <div className="railTitleWithStatus">
              <h1>{service.name}</h1>
              <span className={`railServiceStatus ${service.active_state === "active" ? "railTone-good" : "railTone-warn"}`}>
                <i /> {service.active_state === "active" ? "Running" : service.lifecycle_state}
              </span>
            </div>
            <p dir="ltr">{service.repository ?? service.unit_name}</p>
          </div>
          <Link className="railSecondaryButton" href={`/services/${service.id}`}>Advanced</Link>
        </div>
      </header>

      <nav className="railTabs" aria-label="Service sections">
        {tabs.map(([key, label]) => (
          <Link
            href={`/projects/${project.id}/services/${service.id}?tab=${key}`}
            className={tab === key ? "railTabActive" : ""}
            key={key}
          >
            {label}
          </Link>
        ))}
      </nav>

      {tab === "deployments" && (
        <section className="railServiceSection">
          <div className="railSectionHeader">
            <div><h2>Deployments</h2><p>تاریخچه استقرار این سرویس</p></div>
            {service.lifecycle_state === "managed" ? (
              <form action={deployAction} className="railDeployForm">
                <input type="hidden" name="service_id" value={service.id} />
                <input
                  name="commit"
                  pattern="[0-9a-f]{40}"
                  placeholder="Exact commit (optional)"
                  dir="ltr"
                />
                <button type="submit">Deploy</button>
              </form>
            ) : (
              <Link className="railPrimaryButton" href={`/services/${service.id}`}>Complete setup</Link>
            )}
          </div>

          <div className="railDeploymentList">
            {deployments.length === 0 ? (
              <div className="railEmpty railEmptyCompact">
                <h3>No deployments yet</h3>
                <p>بعد از اولین deploy، تاریخچه releaseها اینجا نمایش داده می‌شود.</p>
              </div>
            ) : deployments.map((deployment) => (
              <Link
                href={`/deployments/${deployment.id}`}
                className="railDeploymentRow"
                key={deployment.id}
              >
                <span className={`railDeployState railDeploy-${deployment.state}`} />
                <div>
                  <strong>{shortCommit(deployment.resolved_commit || deployment.requested_ref)}</strong>
                  <small>{deployment.requested_ref}</small>
                </div>
                <span className="railDeploymentStatus">{deployment.state}</span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {tab === "variables" && (
        <section className="railServiceSection">
          <div className="railSectionHeader">
            <div><h2>Variables</h2><p>Project-level environment variables</p></div>
          </div>
          <div className="railKeyValueList">
            {(project.variables ?? []).length === 0 ? <p className="railMuted">No variables configured.</p> :
              (project.variables ?? []).map((item) => (
                <div key={item.id}>
                  <code>{item.key}</code>
                  <span>{item.value_type === "secret" ? "••••••••" : (item.value ?? "Set")}</span>
                </div>
              ))}
          </div>
        </section>
      )}

      {tab === "logs" && (
        <section className="railServiceSection">
          <div className="railSectionHeader">
            <div><h2>Logs</h2><p>لاگ‌های operational همچنان از مسیر امن typed operations خوانده می‌شوند.</p></div>
            <Link className="railPrimaryButton" href={`/services/${service.id}`}>Open live operations</Link>
          </div>
          <div className="railTerminalPlaceholder" dir="ltr">
            <span>$ DigitalAfarin typed log stream</span>
            <small>Open live operations to request a bounded, redacted journal snapshot.</small>
          </div>
        </section>
      )}

      {tab === "settings" && (
        <ServiceSettingsForm project={project} service={service} />
      )}
    </main>
  );
}
