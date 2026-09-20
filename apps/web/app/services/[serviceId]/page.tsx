import Link from "next/link";
import { deployAction } from "@/app/deployments/actions";
import { configureDeploymentAction } from "@/app/services/adoption-actions";
import { getProject, listDeployments, listProjects } from "@/lib/control-plane";
import { serviceCanDeploy, serviceLifecycleLabel } from "@/lib/service-adoption";

export const dynamic = "force-dynamic";

export default async function ManagedServicePage({ params }: { params: Promise<{ serviceId: string }> }) {
  const { serviceId } = await params;
  const projects = await listProjects();
  const details = await Promise.all(projects.map((item) => getProject(item.id)));
  const service = details.flatMap((item) => item.services ?? []).find((item) => item.id === serviceId);
  if (!service) return <main className="page"><h1>Service not found</h1></main>;
  const deployments = await listDeployments(service.id);
  const inventoryState = service.inventory_status === "missing"
    ? "missing from latest inventory"
    : `${service.active_state ?? "unknown"}/${service.sub_state ?? "unknown"}`;

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
          {service.repository ? <p className="pageLead" dir="ltr">{service.repository} · {service.branch}</p> : null}
        </div>
      </header>

      {service.lifecycle_state !== "managed" ? (
        <section className="panel" style={{ marginBottom: 12 }}>
          <div className="panelHeader">
            <div>
              <h2>Configure deployment</h2>
              <p>Store metadata only. Management remains disabled until Stage B3 controlled takeover.</p>
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
          {service.lifecycle_state === "configured" ? (
            <div className="panelBody">
              <strong>Configured · Management disabled</strong>
              <p>Controlled Takeover is handled in Stage B3.</p>
            </div>
          ) : null}
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
