import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { PageForm } from "@/components/page-form";
import { requireAdmin } from "@/lib/session";
import { listSites } from "@/lib/sites";

export default async function NewPagePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await requireAdmin();
  const query = await searchParams;
  const sites = await listSites(true);
  const requestedSiteId = typeof query.siteId === "string" ? query.siteId : undefined;
  const selected = sites.find((site) => site.id === requestedSiteId) ?? sites[0];
  if (!selected) return <AppShell active="content" title="برگه جدید"><section className="panel empty-state"><h2>سایت فعالی وجود ندارد</h2></section></AppShell>;
  return <AppShell active="content" title="برگه جدید" description={`ساخت Draft برگه در ${selected.name}`} actions={<Link className="button-link secondary" href={`/pages?siteId=${selected.id}`}>بازگشت به برگه‌ها</Link>}>
    <PageForm siteId={selected.id}/>
  </AppShell>;
}
