import Link from "next/link";
import { adoptExistingServiceAction } from "@/app/services/adoption-actions";
import { getProject, listServers, listServices } from "@/lib/control-plane";
import {
  availableInventoryUnits,
  serviceLifecycleLabel,
} from "@/lib/service-adoption";

export const dynamic = "force-dynamic";

export default async function ProjectPage({
  params,
  searchParams,
}: {
  params: Promise<{ projectId: string }>;
  searchParams: Promise<{ server_id?: string }>;
}) {
  const { projectId } = await params;
  const query = await searchParams;
  const project = await getProject(projectId);
  const servers = await listServers();
  const selectedServer =
    servers.find((item) => item.id === query.server_id) ??
    servers.find((item) => item.is_default) ??
    servers[0];
  const inventory = selectedServer ? await listServices(selectedServer.id) : [];
  const available = availableInventoryUnits(
    inventory,
    (project.services ?? []).map((item) => item.unit_name),
  );

  const resources = [
    ["Variables", project.variables ?? [], "key"],
    ["Volumes", project.volumes ?? [], "name"],
    ["Databases", project.databases ?? [], "database_name"],
    ["Domains", project.domains ?? [], "hostname"],
  ] as const;

  return (
    <main className="page">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">PROJECT</p>
          <h1>{project.name}</h1>
          <p className="pageLead"><code>{project.slug}</code></p>
        </div>
      </header>

      <section className="panel" style={{ marginBottom: 12 }}>
        <div className="panelHeader">
          <div>
            <h2>Services</h2>
            <p>{project.services?.length ?? 0} bound services</p>
          </div>
        </div>
        <div className="panelBody">
          {(project.services ?? []).length === 0 ? (
            <p>No services bound to this project yet.</p>
          ) : (
            (project.services ?? []).map((service) => (
              <p key={service.id}>
                <Link href={`/services/${service.id}`}>{service.name}</Link>
                {" · "}<code>{service.unit_name}</code>
                {" · "}{serviceLifecycleLabel(service.lifecycle_state)}
                {" · "}{service.inventory_status === "missing" ? "missing" : (service.active_state ?? "unknown")}
                {service.protected ? " · Protected" : ""}
              </p>
            ))
          )}
        </div>
      </section>

      <section className="panel" style={{ marginBottom: 12 }}>
        <div className="panelHeader">
          <div>
            <h2>Existing services</h2>
            <p>Adopt inventory metadata only. No workload operation is queued.</p>
          </div>
        </div>
        <div className="panelBody">
          <form className="filterBar" method="get">
            <label>
              <span>Server</span>
              <select name="server_id" defaultValue={selectedServer?.id ?? ""}>
                {servers.map((server) => (
                  <option key={server.id} value={server.id}>
                    {server.name}{server.is_default ? " · default" : ""}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit">Load inventory</button>
          </form>

          {selectedServer ? (
            <form className="filterBar" action={adoptExistingServiceAction}>
              <input type="hidden" name="project_id" value={project.id} />
              <input type="hidden" name="server_id" value={selectedServer.id} />
              <label>
                <span>Systemd unit</span>
                <select name="unit_name" required defaultValue="">
                  <option value="" disabled>Select an unbound unit</option>
                  {available.map((item) => (
                    <option key={item.unit_name} value={item.unit_name}>
                      {item.unit_name} · {item.active_state}/{item.sub_state}{item.protected ? " · Protected" : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Project-local name</span>
                <input name="name" required pattern="[A-Za-z0-9_-]{1,80}" placeholder="backend" />
              </label>
              <button type="submit" disabled={available.length === 0}>Adopt metadata</button>
            </form>
          ) : (
            <p>No server is available.</p>
          )}
          {selectedServer && available.length === 0 ? <p>No unbound inventory units on this server.</p> : null}
        </div>
      </section>

      {resources.map(([title, items, key]) => (
        <section className="panel" style={{ marginBottom: 12 }} key={title}>
          <div className="panelHeader"><div><h2>{title}</h2><p>{items.length} item</p></div></div>
          <div className="panelBody">
            {items.map((item) => {
              const record = item as unknown as Record<string, unknown>;
              const label = String(record[key]);
              return (
                <p key={String(record.id)}>
                  <code>{label}</code>{record.value_type === "secret" ? " • hidden" : ""}
                </p>
              );
            })}
          </div>
        </section>
      ))}
    </main>
  );
}
