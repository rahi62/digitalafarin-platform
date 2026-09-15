import Link from "next/link";
import { getProject, listDeployments, listProjects } from "@/lib/control-plane";
import { deployAction } from "@/app/deployments/actions";

export const dynamic = "force-dynamic";

export default async function ManagedServicePage({ params }: { params: Promise<{ serviceId: string }> }) {
  const { serviceId } = await params;
  const projects = await listProjects();
  const details = await Promise.all(projects.map((item) => getProject(item.id)));
  const service = details.flatMap((item) => item.services ?? []).find((item) => item.id === serviceId);
  if (!service) return <main className="page"><h1>Service not found</h1></main>;
  const deployments = await listDeployments(service.id);
  return <main className="page"><header className="pageHeader"><div><p className="eyebrow">SERVICE</p><h1>{service.name}</h1><p className="pageLead" dir="ltr">{service.repository} · {service.branch}</p></div></header>
    <section className="panel" style={{ marginBottom: 12 }}><div className="panelHeader"><div><h2>Deploy</h2><p>Latest branch or exact commit</p></div></div><form className="filterBar" action={deployAction}><input type="hidden" name="service_id" value={service.id}/><label><span>Exact commit (optional)</span><input name="commit" pattern="[0-9a-f]{40}" /></label><button type="submit">Deploy</button></form></section>
    <section className="panel"><div className="panelHeader"><div><h2>Deployments</h2><p>{deployments.length} records</p></div></div><div className="panelBody">{deployments.map((item) => <p key={item.id}><Link href={`/deployments/${item.id}`}>{item.resolved_commit || item.requested_ref}</Link> · {item.state}</p>)}</div></section>
  </main>;
}
