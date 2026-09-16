import { getMetrics, getProject, listDeployments, listOperations, listProjects, listServers } from "@/lib/control-plane";
import { deriveMigrationReadiness } from "@/lib/migration-readiness";

export const dynamic = "force-dynamic";

export default async function MigrationPage() {
  const [servers, projectSummaries, operations] = await Promise.all([listServers(), listProjects(), listOperations()]);
  const projects = await Promise.all(projectSummaries.map((project) => getProject(project.id)));
  const services = projects.flatMap((project) => project.services ?? []);
  const [metrics, deploymentGroups] = await Promise.all([
    Promise.all(servers.map((server) => getMetrics(server.id))),
    Promise.all(services.map((service) => listDeployments(service.id))),
  ]);
  const steps = deriveMigrationReadiness(servers, projects, {
    operations,
    deployments: deploymentGroups.flat(),
    metrics,
  });
  return <main className="page"><header className="pageHeader"><div><p className="eyebrow">MIGRATION READINESS</p><h1>مهاجرت VPS</h1><p className="pageLead">وضعیت واقعی منابع و مراحل cutover به ترتیب اجرایی.</p></div></header>
    <section className="panel"><div className="auditList">{steps.map((step, index) => <div className="auditRow" key={step.label}><strong>{index + 1}. {step.label}</strong><span>{step.detail}</span><code>{step.state}</code></div>)}</div></section>
  </main>;
}
