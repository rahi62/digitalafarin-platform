import Link from "next/link";
import { getProject } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function ProjectPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  const project = await getProject(projectId);
  const sections = [
    ["Services", project.services ?? [], "name"], ["Variables", project.variables ?? [], "key"],
    ["Volumes", project.volumes ?? [], "name"], ["Databases", project.databases ?? [], "database_name"],
    ["Domains", project.domains ?? [], "hostname"],
  ] as const;
  return <main className="page"><header className="pageHeader"><div><p className="eyebrow">PROJECT</p><h1>{project.name}</h1><p className="pageLead"><code>{project.slug}</code></p></div></header>
    {sections.map(([title, items, key]) => <section className="panel" style={{ marginBottom: 12 }} key={title}><div className="panelHeader"><div><h2>{title}</h2><p>{items.length} item</p></div></div><div className="panelBody">{items.map((item) => {
      const record = item as unknown as Record<string, unknown>;
      const label = String(record[key]);
      return title === "Services" ? <p key={String(record.id)}><Link href={`/services/${record.id}`}>{label}</Link></p> : <p key={String(record.id)}><code>{label}</code>{record.value_type === "secret" ? " • hidden" : ""}</p>;
    })}</div></section>)}
  </main>;
}
