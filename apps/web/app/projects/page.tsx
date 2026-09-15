import Link from "next/link";
import { listProjects } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function ProjectsPage() {
  const projects = await listProjects().catch(() => []);
  return <main className="page"><header className="pageHeader"><div><p className="eyebrow">MIGRATION PROJECTS</p><h1>پروژه‌ها</h1><p className="pageLead">سرویس‌ها و منابع قابل بازیابی روی VPS مقصد.</p></div></header>
    <section className="panel"><div className="panelBody serverCards">{projects.map((project) => <Link className="serverCard" href={`/projects/${project.id}`} key={project.id}><strong>{project.name}</strong><code>{project.slug}</code></Link>)}</div></section>
  </main>;
}
