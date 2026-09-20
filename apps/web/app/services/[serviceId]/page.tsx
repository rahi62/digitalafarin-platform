import Link from "next/link";
import { deployAction } from "@/app/deployments/actions";
import { configureDeploymentAction } from "@/app/services/adoption-actions";
import {
  activateTakeoverAction,
  cancelTakeoverAction,
  prepareTakeoverAction,
} from "@/app/services/takeover-actions";
import {
  getProject,
  listDeployments,
  listProjects,
  listServiceTakeovers,
} from "@/lib/control-plane";
import { serviceCanDeploy, serviceLifecycleLabel } from "@/lib/service-adoption";
import {
  canActivateTakeover,
  canPrepareTakeover,
  takeoverStateLabel,
  type TakeoverState,
} from "@/lib/takeovers";

export const dynamic = "force-dynamic";

const ACTIVE_TAKEOVER_STATES = new Set<TakeoverState>([
  "queued",
  "inspecting",
  "preparing",
  "prepared",
  "activating",
  "verifying",
]);

function stringField(value: unknown) {
  return typeof value === "string" ? value : "—";
}

export default async function ManagedServicePage({
  params,
}: {
  params: Promise<{ serviceId: string }>;
}) {
  const { serviceId } = await params;
  const projects = await listProjects();
  const details = await Promise.all(projects.map((item) => getProject(item.id)));
  const service = details
    .flatMap((item) => item.services ?? [])
    .find((item) => item.id === serviceId);
  if (!service) {
    return <main className="page"><h1>Service not found</h1></main>;
  }

  const project = details.find((item) => item.id === service.project_id);
  const [deployments, takeovers] = await Promise.all([
    listDeployments(service.id),
    listServiceTakeovers(service.id),
  ]);
  const activeTakeover = takeovers.find((item) => ACTIVE_TAKEOVER_STATES.has(item.state));
  const latestTakeover = activeTakeover ?? takeovers[0];
  const inventoryState = service.inventory_status === "missing"
    ? "missing from latest inventory"
    : `${service.active_state ?? "unknown"}/${service.sub_state ?? "unknown"}`;

  const sourceWorkingDirectory = latestTakeover
    ? stringField(latestTakeover.source_snapshot.working_directory)
    : "—";
  const healthUrl = latestTakeover
    ? stringField(latestTakeover.health_check_snapshot.url)
    : "—";
  const proposedWorkingDirectory = project && service.root_directory
    ? `/srv/digitalafarin/apps/${project.slug}/${service.name}/current/${service.root_directory}`
    : "—";

  return (
    <main className="page">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">SERVICE</p>
          <h1>{service.name}</h1>
          <p className="pageLead" dir="ltr">
            <code>{service.unit_name}</code> · {serviceLifecycleLabel(service.lifecycle_state)} · {inventoryState}
            {service.protected ? " · Protected" : ""}
          </p>
          {service.repository ? (
            <p className="pageLead" dir="ltr">{service.repository} · {service.branch}</p>
          ) : null}
        </div>
      </header>

      {service.lifecycle_state === "adopted" ? (
        <section className="panel" style={{ marginBottom: 12 }}>
          <div className="panelHeader">
            <div>
              <h2>Configure deployment</h2>
              <p>Store deployment metadata only. This does not enable management or restart the service.</p>
            </div>
          </div>
          <form className="panelBody" action={configureDeploymentAction}>
            <input type="hidden" name="service_id" value={service.id} />
            <div className="filterBar">
              <label><span>Repository URL</span><input name="repository" type="url" required defaultValue={service.repository ?? ""} /></label>
              <label><span>Branch</span><input name="branch" required defaultValue={service.branch ?? "main"} /></label>
              <label><span>Root directory</span><input name="root_directory" required defaultValue={service.root_directory ?? "."} /></label>
              <label>
                <span>Runtime</span>
                <select name="runtime" required defaultValue={service.runtime ?? "node-nextjs"}>
                  <option value="node-nextjs">Node / Next.js</option>
                  <option value="python-django">Python / Django</option>
                </select>
              </label>
              <label><span>Service port</span><input name="service_port" type="number" min="1" max="65535" required defaultValue={service.service_port ?? undefined} /></label>
            </div>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span>Install configuration JSON</span>
              <textarea name="install_configuration" rows={5} defaultValue={JSON.stringify(service.install_configuration ?? {}, null, 2)} />
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span>Build configuration JSON</span>
              <textarea name="build_configuration" rows={6} defaultValue={JSON.stringify(service.build_configuration ?? {}, null, 2)} />
            </label>
            <button type="submit">Save deployment metadata</button>
          </form>
        </section>
      ) : null}

      {canPrepareTakeover(service.lifecycle_state) ? (
        <section className="panel" style={{ marginBottom: 12 }}>
          <div className="panelHeader">
            <div>
              <h2>Controlled takeover</h2>
              <p>Prepare is non-mutating. Activation is a separate explicit step after the exact release and source fingerprint are persisted.</p>
            </div>
          </div>
          <div className="panelBody">
            <p dir="ltr"><strong>Unit:</strong> <code>{service.unit_name}</code></p>
            <p dir="ltr"><strong>Runtime:</strong> {service.runtime ?? "—"} · <strong>Protected:</strong> {service.protected ? "yes" : "no"} · <strong>Inventory:</strong> {service.inventory_status}</p>
            <p dir="ltr"><strong>Repository:</strong> {service.repository ?? "—"} · <strong>Branch:</strong> {service.branch ?? "—"}</p>
            <p dir="ltr"><strong>Root:</strong> {service.root_directory ?? "—"} · <strong>Port:</strong> {service.service_port ?? "—"}</p>

            {latestTakeover ? (
              <div style={{ marginTop: 16 }}>
                <strong>{takeoverStateLabel(latestTakeover.state)}</strong>
                <p dir="ltr"><strong>Requested commit:</strong> <code>{latestTakeover.requested_commit}</code></p>
                {latestTakeover.failure_code ? (
                  <p dir="ltr"><strong>Failure:</strong> {latestTakeover.failure_code} · {latestTakeover.failure_message}</p>
                ) : null}
              </div>
            ) : null}

            {latestTakeover?.state === "prepared" ? (
              <div style={{ marginTop: 16 }}>
                <h3>Prepared takeover</h3>
                <p dir="ltr"><strong>Resolved commit:</strong> <code>{latestTakeover.resolved_commit}</code></p>
                <p dir="ltr"><strong>Source fingerprint:</strong> <code>{latestTakeover.source_fingerprint}</code></p>
                <p dir="ltr"><strong>Release:</strong> <code>{latestTakeover.release_name}</code></p>
                <p dir="ltr"><strong>Current source working directory:</strong> <code>{sourceWorkingDirectory}</code></p>
                <p dir="ltr"><strong>Proposed managed working directory:</strong> <code>{proposedWorkingDirectory}</code></p>
                <p dir="ltr"><strong>Health target:</strong> <code>{healthUrl}</code></p>

                {!latestTakeover.activate_operation_id && canActivateTakeover(latestTakeover.state) ? (
                  <div className="filterBar">
                    <form action={activateTakeoverAction}>
                      <input type="hidden" name="service_id" value={service.id} />
                      <input type="hidden" name="takeover_id" value={latestTakeover.id} />
                      <button type="submit">Activate controlled takeover</button>
                    </form>
                    <form action={cancelTakeoverAction}>
                      <input type="hidden" name="service_id" value={service.id} />
                      <input type="hidden" name="takeover_id" value={latestTakeover.id} />
                      <button type="submit">Cancel prepared takeover</button>
                    </form>
                  </div>
                ) : (
                  <p>Activation is queued or already running. No duplicate action is available.</p>
                )}
              </div>
            ) : null}

            {!activeTakeover ? (
              <form action={prepareTakeoverAction} className="filterBar" style={{ marginTop: 16 }}>
                <input type="hidden" name="service_id" value={service.id} />
                <label>
                  <span>Exact production commit</span>
                  <input
                    name="commit"
                    pattern="[0-9a-f]{40}"
                    minLength={40}
                    maxLength={40}
                    required
                    placeholder="40-character lowercase Git SHA"
                  />
                </label>
                <button type="submit">Prepare controlled takeover</button>
              </form>
            ) : null}
          </div>
        </section>
      ) : null}

      {serviceCanDeploy(service.lifecycle_state) ? (
        <section className="panel" style={{ marginBottom: 12 }}>
          <div className="panelHeader"><div><h2>Deploy</h2><p>Latest branch or exact commit</p></div></div>
          <form className="filterBar" action={deployAction}>
            <input type="hidden" name="service_id" value={service.id}/>
            <label><span>Exact commit (optional)</span><input name="commit" pattern="[0-9a-f]{40}" /></label>
            <button type="submit">Deploy</button>
          </form>
        </section>
      ) : null}

      {takeovers.length ? (
        <section className="panel" style={{ marginBottom: 12 }}>
          <div className="panelHeader"><div><h2>Takeovers</h2><p>{takeovers.length} records</p></div></div>
          <div className="panelBody">
            {takeovers.map((item) => (
              <p key={item.id} dir="ltr">
                <code>{item.requested_commit}</code> · {takeoverStateLabel(item.state)}
              </p>
            ))}
          </div>
        </section>
      ) : null}

      <section className="panel">
        <div className="panelHeader"><div><h2>Deployments</h2><p>{deployments.length} records</p></div></div>
        <div className="panelBody">
          {deployments.map((item) => (
            <p key={item.id}>
              <Link href={`/deployments/${item.id}`}>{item.resolved_commit || item.requested_ref}</Link> · {item.state}
            </p>
          ))}
        </div>
      </section>
    </main>
  );
}
