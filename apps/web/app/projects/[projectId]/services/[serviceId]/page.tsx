import Link from "next/link";
import { randomUUID } from 'node:crypto';
import { RetryProvision } from '../new/RetryProvision';
import { deployAction } from "@/app/deployments/actions";
import { getProject, getOperation, listDeployments } from "@/lib/control-plane";
import { lifecycleLabel } from '@/lib/provisioning';
import { OperationRefresh } from '@/components/OperationRefresh';
import { DeploymentProgress } from '@/components/DeploymentProgress';
import { queueServiceOperation } from '@/app/operations/actions';

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
  const provisioning = service.provisioning_operation_id ? await getOperation(service.provisioning_operation_id) : null;
  const activeProvision = provisioning ? ['queued', 'claimed', 'running'].includes(provisioning.state) : ['pending', 'provisioning'].includes(service.lifecycle_state);

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
              <span className={`railServiceStatus ${service.lifecycle_state === 'provision_failed' ? 'railTone-bad' : service.active_state === "active" && service.lifecycle_state === 'managed' ? "railTone-good" : "railTone-warn"}`}>
                <i /> {service.active_state === "active" && service.lifecycle_state === 'managed' ? "Running" : lifecycleLabel(service.lifecycle_state)}
              </span>
            </div>
            <p dir="ltr">{service.repository ?? service.unit_name}</p>
          </div>
          <Link className="railSecondaryButton" href={`/services/${service.id}`}>Advanced</Link>
        </div>
      </header>

      <OperationRefresh active={activeProvision} />
      {provisioning && service.lifecycle_state !== 'managed' && <section className="provisionStatus" role={service.lifecycle_state === 'provision_failed' ? 'alert' : 'status'}>
        <strong>{lifecycleLabel(service.lifecycle_state)}</strong>
        <p>{service.lifecycle_state === 'provision_failed' ? 'راه‌اندازی سرویس کامل نشد. جزئیات عملیات را بررسی کنید.' : 'درخواست شما ثبت شده است. وضعیت از سرور دریافت و به‌صورت خودکار بروزرسانی می‌شود.'}</p>
        <DeploymentProgress operation={provisioning} />
        <Link href={`/operations/${provisioning.id}`}>مشاهدهٔ جزئیات عملیات ←</Link>
        {service.lifecycle_state === 'provision_failed' && <form action={queueServiceOperation}>
          <input type="hidden" name="server_id" value={service.target_server_id} />
          <input type="hidden" name="unit_name" value={service.unit_name} />
          <input type="hidden" name="action" value="logs" />
          <button type="submit" className="railSecondaryButton">مشاهدهٔ لاگ خطا</button>
        </form>}
        {service.lifecycle_state === 'provision_failed' && <RetryProvision projectId={project.id} serviceId={service.id} requestId={randomUUID()} />}
      </section>}

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
            ) : ['pending', 'provisioning', 'provision_failed'].includes(service.lifecycle_state) ? (
              provisioning ? <Link className="railPrimaryButton" href={`/operations/${provisioning.id}`}>View provisioning</Link> : null
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
            <form action={queueServiceOperation}>
              <input type="hidden" name="server_id" value={service.target_server_id} />
              <input type="hidden" name="unit_name" value={service.unit_name} />
              <input type="hidden" name="action" value="logs" />
              <button type="submit" className="railPrimaryButton">دریافت آخرین لاگ‌ها</button>
            </form>
          </div>
          <div className="railTerminalPlaceholder" dir="ltr">
            <span>$ journalctl --unit {service.unit_name}</span>
            <small>آخرین ۱۰۰ خط لاگ سرویس پس از پالایش اطلاعات حساس نمایش داده می‌شود.</small>
          </div>
        </section>
      )}

      {tab === "settings" && (
        <section className="railServiceSection">
          <div className="railSectionHeader">
            <div><h2>Settings</h2><p>تنظیمات اصلی deployment بدون نمایش جزئیات داخلی Control Plane</p></div>
          </div>
          <div className="railSettingsGrid">
            <div><span>Repository</span><code dir="ltr">{service.repository ?? "—"}</code></div>
            <div><span>Branch</span><code dir="ltr">{service.branch ?? "—"}</code></div>
            <div><span>Runtime</span><strong>{service.runtime ?? "—"}</strong></div>
            <div><span>Port</span><strong>{service.service_port ?? "—"}</strong></div>
            <div><span>Root directory</span><code dir="ltr">{service.root_directory ?? "—"}</code></div>
            <div><span>Lifecycle</span><strong>{service.lifecycle_state}</strong></div>
            <div><span>Systemd unit</span><code dir="ltr">{service.unit_name}</code></div>
            <div><span>Server</span><code dir="ltr">{service.target_server_id}</code></div>
          </div>
        </section>
      )}
    </main>
  );
}
