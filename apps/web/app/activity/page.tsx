import { AuditList } from "@/components/AuditList";
import { EmptyState } from "@/components/EmptyState";
import { listAuditEvents, listServers } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function ActivityPage({ searchParams }: { searchParams: Promise<{ server?: string }> }) {
  const query = await searchParams;
  const servers = await listServers().catch(() => []);
  const selectedId = query.server && servers.some((server) => server.id === query.server) ? query.server : "";
  const events = await listAuditEvents({ serverId: selectedId || undefined, limit: 50 }).catch(() => []);

  return (
    <main className="page">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">AUDIT TRAIL</p>
          <h1>فعالیت‌ها</h1>
          <p className="pageLead">رویدادهای خواندن MCP، heartbeatهای Agent و فعالیت‌های Control Plane با actor قابل ردیابی.</p>
        </div>
      </header>

      <form className="filterBar" method="get">
        <label>
          <span>محدوده</span>
          <select name="server" defaultValue={selectedId}>
            <option value="">همه سرورها و Control Plane</option>
            {servers.map((server) => <option value={server.id} key={server.id}>{server.name}</option>)}
          </select>
        </label>
        <button type="submit">اعمال</button>
      </form>

      <section className="panel">
        <div className="panelHeader">
          <div><h2>Audit events</h2><p>۵۰ رویداد آخر{selectedId ? " برای سرور انتخاب‌شده" : " در کل پلتفرم"}</p></div>
          <span className="countPill">{events.length}</span>
        </div>
        {events.length > 0 ? <AuditList events={events} /> : <EmptyState title="رویدادی پیدا نشد" description="در محدوده فعلی Audit event قابل مشاهده‌ای وجود ندارد." />}
      </section>
    </main>
  );
}
