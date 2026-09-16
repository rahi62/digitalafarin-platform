import { getMetrics, getProject, listDeployments, listOperations, listProjects, listServers } from "@/lib/control-plane";
import { loadMigrationReadiness } from "@/lib/migration-page";

export const dynamic = "force-dynamic";

export default async function MigrationPage() {
  const steps = await loadMigrationReadiness({
    listServers,
    listProjects,
    listOperations,
    getProject,
    getMetrics,
    listDeployments,
  });
  return <main className="page"><header className="pageHeader"><div><p className="eyebrow">MIGRATION READINESS</p><h1>مهاجرت VPS</h1><p className="pageLead">وضعیت واقعی منابع و مراحل cutover به ترتیب اجرایی.</p></div></header>
    <section className="panel"><div className="auditList">{steps.map((step, index) => <div className="auditRow" key={step.label}><strong>{index + 1}. {step.label}</strong><span>{step.detail}</span><code>{step.state}</code></div>)}</div></section>
  </main>;
}
