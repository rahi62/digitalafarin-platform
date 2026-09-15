import { getDeployment } from "@/lib/control-plane";
import { redeployAction, rollbackAction } from "../actions";

export const dynamic = "force-dynamic";

export default async function DeploymentPage({ params }: { params: Promise<{ deploymentId: string }> }) {
  const { deploymentId } = await params;
  const deployment = await getDeployment(deploymentId);
  return <main className="page"><header className="pageHeader"><div><p className="eyebrow">DEPLOYMENT</p><h1>{deployment.state}</h1><p className="pageLead"><code>{deployment.resolved_commit || deployment.requested_ref}</code></p></div><div className="pageActions"><form action={redeployAction}><input type="hidden" name="deployment_id" value={deployment.id}/><button>Redeploy</button></form><form action={rollbackAction}><input type="hidden" name="deployment_id" value={deployment.id}/><button>Rollback</button></form></div></header>
    <section className="panel"><div className="panelHeader"><div><h2>Events</h2><p>Active release: {deployment.active_release ?? "—"}</p></div></div><div className="auditList">{(deployment.events ?? []).map((event) => <div className="auditRow" key={event.id}><code>{event.state}</code><span>{event.message}</span><time>{new Date(event.created_at).toLocaleString()}</time></div>)}</div></section>
  </main>;
}
