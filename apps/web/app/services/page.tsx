import Link from "next/link";
import { EmptyState } from "@/components/EmptyState";
import { ServiceTable } from "@/components/ServiceTable";
import { StatusBadge } from "@/components/StatusBadge";
import { getServer, listServers, listServices } from "@/lib/control-plane";
import { summarizeServices } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

const allowedStatuses = new Set(["active", "failed", "inactive"]);

export default async function ServicesPage({ searchParams }: { searchParams: Promise<{ server?: string; status?: string }> }) {
  const query = await searchParams;
  const servers = await listServers().catch(() => []);
  const requestedServer = query.server || "default";
  const status = query.status && allowedStatuses.has(query.status) ? query.status : undefined;
  const server = await getServer(requestedServer).catch(() => null);
  const services = server ? await listServices(server.id, status).catch(() => []) : [];
  const allServices = server && status ? await listServices(server.id).catch(() => services) : services;
  const summary = summarizeServices(allServices);

  const filters = [
    { key: "", label: "همه" },
    { key: "active", label: "فعال" },
    { key: "failed", label: "خطادار" },
    { key: "inactive", label: "غیرفعال" },
  ];

  return (
    <main className="page">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">SYSTEMD INVENTORY</p>
          <h1>سرویس‌ها</h1>
          <p className="pageLead">مشاهده سرویس‌های allow-listed هر VPS و تشخیص سریع سرویس‌های failed یا inactive.</p>
        </div>
        {server ? <div className="pageActions"><StatusBadge status={server.status} /></div> : null}
      </header>

      <form className="filterBar" method="get">
        <label>
          <span>سرور</span>
          <select name="server" defaultValue={server?.id ?? requestedServer}>
            {servers.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
          </select>
        </label>
        {status ? <input type="hidden" name="status" value={status} /> : null}
        <button type="submit">اعمال</button>
      </form>

      {server ? (
        <>
          <div className="kpiStrip" style={{ marginBottom: 12 }}>
            <div className="kpiItem"><strong>{summary.total}</strong><span>کل سرویس‌ها</span></div>
            <div className="kpiItem"><strong>{summary.active}</strong><span>فعال</span></div>
            <div className="kpiItem"><strong>{summary.failed}</strong><span>خطادار</span></div>
            <div className="kpiItem"><strong>{summary.inactive}</strong><span>غیرفعال</span></div>
          </div>

          <div className="filters">
            {filters.map((filter) => {
              const href = filter.key
                ? `/services?server=${encodeURIComponent(server.id)}&status=${filter.key}`
                : `/services?server=${encodeURIComponent(server.id)}`;
              const active = (status ?? "") === filter.key;
              return <Link className={`filterChip ${active ? "filterChipActive" : ""}`} href={href} key={filter.key}>{filter.label}</Link>;
            })}
          </div>

          <section className="panel">
            <div className="panelHeader">
              <div><h2>{server.name}</h2><p dir="ltr">{server.hostname}</p></div>
              <span className="countPill">{services.length} item</span>
            </div>
            <ServiceTable services={services} />
          </section>
        </>
      ) : (
        <section className="panel errorPanel"><EmptyState title="سرور در دسترس نیست" description="سرور انتخاب‌شده در Control Plane resolve نشد." /></section>
      )}
    </main>
  );
}
