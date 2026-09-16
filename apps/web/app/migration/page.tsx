import { randomUUID } from "node:crypto";

import { getMetrics, getProject, listDeployments, listOperations, listProjects, listServers } from "@/lib/control-plane";
import { loadMigrationReadiness } from "@/lib/migration-page";
import { createMigrationProject, queueBootstrap } from "./actions";

export const dynamic = "force-dynamic";

export default async function MigrationPage({ searchParams }: { searchParams: Promise<{ project?: string }> }) {
  const query = await searchParams;
  const [servers, projects] = await Promise.all([listServers(), listProjects()]);
  const selectedProjectId = projects.some((project) => project.id === query.project)
    ? query.project
    : projects.length === 1
      ? projects[0].id
      : undefined;
  const steps = await loadMigrationReadiness({
    listServers: async () => servers,
    listProjects: async () => projects,
    listOperations,
    getProject,
    getMetrics,
    listDeployments,
  }, selectedProjectId);

  return <main className="page">
    <header className="pageHeader"><div><p className="eyebrow">MIGRATION READINESS</p><h1>مهاجرت VPS</h1><p className="pageLead">وضعیت واقعی منابع و مراحل cutover به ترتیب اجرایی.</p></div></header>

    <section className="panel" style={{ marginBottom: 12 }}>
      <div className="panelHeader"><div><h2>Bootstrap</h2><p>عملیات typed و بدون shell آزاد روی سرور مقصد.</p></div></div>
      <div className="auditList">
        {servers.map((server) => <div className="auditRow" key={server.id}>
          <strong>{server.name}</strong>
          <span>{server.hostname || server.id}</span>
          <form action={queueBootstrap}>
            <input type="hidden" name="server_id" value={server.id} />
            <input type="hidden" name="idempotency_key" value={`migration-bootstrap-${randomUUID()}`} />
            <button type="submit" disabled={server.status !== "online"}>Queue bootstrap</button>
          </form>
        </div>)}
      </div>
    </section>

    <section className="panel" style={{ marginBottom: 12 }}>
      <div className="panelHeader"><div><h2>پروژه مقصد</h2><p>یک پروژه موجود را انتخاب کن یا پروژه جدید بساز.</p></div></div>
      {projects.length > 0 ? <form className="filterBar" action="/migration" method="get">
        <label><span>Project</span><select name="project" defaultValue={selectedProjectId ?? ""}>
          {!selectedProjectId && <option value="">انتخاب پروژه</option>}
          {projects.map((project) => <option key={project.id} value={project.id}>{project.name} · {project.slug}</option>)}
        </select></label>
        <button type="submit">Select</button>
      </form> : null}
      <form className="filterBar" action={createMigrationProject}>
        <label><span>نام</span><input name="name" required maxLength={120} placeholder="Oily" /></label>
        <label><span>Slug</span><input name="slug" required maxLength={80} pattern="[a-z0-9]+(?:[-_][a-z0-9]+)*" placeholder="oily" dir="ltr" /></label>
        <button type="submit">Create project</button>
      </form>
    </section>

    <section className="panel"><div className="auditList">{steps.map((step, index) => <div className="auditRow" key={step.label}><strong>{index + 1}. {step.label}</strong><span>{step.detail}</span><code>{step.state}</code></div>)}</div></section>
  </main>;
}
