import Link from 'next/link';
import { randomUUID } from 'node:crypto';
import { getProject, listServers } from '@/lib/control-plane';
import { ProvisionForm } from './ProvisionForm';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'ساخت سرویس' };

export default async function NewServicePage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  const [project, servers] = await Promise.all([getProject(projectId), listServers()]);
  return <main className="railPage provisionPage">
    <header className="provisionHeader"><Link href={`/projects/${project.id}`}>→ بازگشت به {project.name}</Link>
      <h1>از مخزن تا سرویس آماده</h1><p>برنامه‌تان را انتخاب کنید؛ ساخت، راه‌اندازی و بررسی سلامت را از همین‌جا دنبال کنید.</p></header>
    <ProvisionForm projectId={project.id} requestId={randomUUID()} servers={servers} />
  </main>;
}
