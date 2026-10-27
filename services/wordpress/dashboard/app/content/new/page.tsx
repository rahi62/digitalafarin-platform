import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { DraftForm } from "@/components/draft-form";
import { requireAdmin } from "@/lib/session";
import { getSiteConnection, listSites } from "@/lib/sites";
import { listWordPressCategories } from "@/lib/wordpress";

export default async function NewDraftPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await requireAdmin();
  const params = await searchParams;
  const sites = await listSites(true);
  const requestedSiteId = typeof params.siteId === "string" ? params.siteId : undefined;
  const selected = sites.find((site) => site.id === requestedSiteId) ?? sites[0];
  if (!selected) return <AppShell active="content" title="نوشته جدید"><section className="panel empty-state"><h2>سایت فعالی وجود ندارد</h2><Link className="button-link primary" href="/sites">افزودن سایت</Link></section></AppShell>;
  const connection = await getSiteConnection(selected.id);
  const categories = await listWordPressCategories(connection).catch(() => []);
  return <AppShell active="content" title="نوشته جدید" description={`ایجاد پیش‌نویس امن در ${selected.name}`} actions={<Link className="button-link secondary" href={`/content?siteId=${selected.id}`}>بازگشت به محتوا</Link>}>
    <DraftForm siteId={selected.id} categories={categories} />
  </AppShell>;
}
