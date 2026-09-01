import { SyncButton } from "@/components/SyncButton";
import { getServer } from "@/lib/api";

function formatUptime(seconds: number) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return days > 0 ? `${days} روز و ${hours} ساعت` : `${hours} ساعت`;
}

function MetricCard({ label, value, suffix = "%" }: { label: string; value: number | string; suffix?: string }) {
  return (
    <article className="metricCard">
      <span>{label}</span>
      <strong>{value}{suffix}</strong>
    </article>
  );
}

export default async function Home() {
  const server = await getServer();

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brandMark">DA</span>
          <div><strong>DigitalAfarin</strong><small>Platform</small></div>
        </div>
        <nav>
          <a className="active">Overview</a>
          <a>Applications</a>
          <a>Databases</a>
          <a>Domains</a>
          <a>Backups</a>
          <a>Activity</a>
          <a>Settings</a>
        </nav>
        <div className="phaseBadge">MVP · Read only</div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">PERSONAL VPS CONTROL PLANE</p>
            <h1>{server?.name ?? "DigitalAfarin Server"}</h1>
            <p className="muted">{server?.hostname || "API هنوز به سرور متصل نشده است."}</p>
          </div>
          <SyncButton />
        </header>

        {!server ? (
          <div className="emptyState">
            <strong>Control Plane آماده است، اما Server record پیدا نشد.</strong>
            <code>python manage.py seed_local_server --agent-url http://127.0.0.1:9743</code>
          </div>
        ) : (
          <>
            <div className="metricsGrid">
              <MetricCard label="CPU" value={server.cpu_percent} />
              <MetricCard label="RAM" value={server.memory_percent} />
              <MetricCard label="Disk" value={server.disk_percent} />
              <MetricCard label="Uptime" value={formatUptime(server.uptime_seconds)} suffix="" />
            </div>

            <section className="panel">
              <div className="panelHeader">
                <div>
                  <p className="eyebrow">SYSTEMD INVENTORY</p>
                  <h2>Services</h2>
                </div>
                <span className="countBadge">{server.services.length}</span>
              </div>

              <div className="serviceList">
                {server.services.length === 0 ? (
                  <div className="emptyInline">هیچ سرویسی با prefixهای مجاز Agent پیدا نشده است.</div>
                ) : server.services.map((service) => {
                  const healthy = service.active_state === "active";
                  return (
                    <article className="serviceRow" key={service.id}>
                      <span className={`statusDot ${healthy ? "up" : "down"}`} />
                      <div className="serviceMain">
                        <strong dir="ltr">{service.unit_name}</strong>
                        <span>{service.description}</span>
                      </div>
                      <div className="serviceState" dir="ltr">
                        <strong>{service.active_state}</strong>
                        <span>{service.sub_state}</span>
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>

            <footer>
              Last sync: {server.last_seen_at ? new Date(server.last_seen_at).toLocaleString("fa-IR") : "never"}
            </footer>
          </>
        )}
      </section>
    </main>
  );
}
