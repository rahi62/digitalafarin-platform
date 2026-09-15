import Link from "next/link";
import { EmptyState } from "@/components/EmptyState";
import { MetricCard } from "@/components/MetricCard";
import { ServiceTable } from "@/components/ServiceTable";
import { StatusBadge } from "@/components/StatusBadge";
import { ControlPlaneError, getMetrics, getServer, listServices } from "@/lib/control-plane";
import { formatAge, formatPercent, formatUptime, summarizeServices } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

function metricState(value: number, warning: number, danger: number): "normal" | "warning" | "danger" {
  if (value >= danger) return "danger";
  if (value >= warning) return "warning";
  return "normal";
}

export default async function ServerDetailPage({ params }: { params: Promise<{ serverId: string }> }) {
  const { serverId } = await params;

  let server;
  try {
    server = await getServer(serverId);
  } catch (error) {
    return (
      <main className="page">
        <header className="pageHeader"><div><p className="eyebrow">SERVER DETAIL</p><h1>سرور پیدا نشد</h1></div></header>
        <section className="panel errorPanel">
          <EmptyState
            title="امکان خواندن این سرور وجود ندارد"
            description={error instanceof ControlPlaneError ? error.message : "Control Plane پاسخ معتبر برنگرداند."}
          />
        </section>
      </main>
    );
  }

  const [metricsResult, servicesResult] = await Promise.allSettled([
    getMetrics(server.id),
    listServices(server.id),
  ]);
  const metrics = metricsResult.status === "fulfilled" ? metricsResult.value : null;
  const services = servicesResult.status === "fulfilled" ? servicesResult.value : [];
  const summary = summarizeServices(services);
  const metricsMessage = metricsResult.status === "rejected" && metricsResult.reason instanceof ControlPlaneError
    ? metricsResult.reason.message
    : "Metrics در حال حاضر در دسترس نیست.";

  return (
    <main className="page">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">SERVER DETAIL</p>
          <h1>{server.name}</h1>
          <p className="pageLead" dir="ltr">{server.hostname}</p>
        </div>
        <div className="pageActions"><StatusBadge status={server.status} /></div>
      </header>

      {server.status !== "online" ? (
        <div className="notice">آخرین heartbeat {formatAge(server.age_seconds)} دریافت شده است. داده‌های این صفحه ممکن است تازه نباشند.</div>
      ) : null}

      <div className="metricsGrid">
        <MetricCard label="CPU" value={metrics ? formatPercent(metrics.cpu_percent) : "—"} level={metrics?.cpu_percent} state={metrics ? metricState(metrics.cpu_percent, 70, 90) : "warning"} hint={metrics ? `نمونه ${formatAge(metrics.age_seconds)}` : metricsMessage} />
        <MetricCard label="RAM" value={metrics ? formatPercent(metrics.memory_percent) : "—"} level={metrics?.memory_percent} state={metrics ? metricState(metrics.memory_percent, 75, 90) : "warning"} hint={`Agent v${server.agent_version || "—"}`} />
        <MetricCard label="Disk" value={metrics ? formatPercent(metrics.disk_percent) : "—"} level={metrics?.disk_percent} state={metrics ? metricState(metrics.disk_percent, 75, 90) : "warning"} hint="پارتیشن اصلی" />
        <MetricCard label="Uptime" value={metrics ? formatUptime(metrics.uptime_seconds) : "—"} hint={metrics ? `Heartbeat ${formatAge(metrics.age_seconds)}` : metricsMessage} />
      </div>

      <div className="kpiStrip" style={{ marginTop: 12 }}>
        <div className="kpiItem"><strong>{summary.total}</strong><span>کل سرویس‌ها</span></div>
        <div className="kpiItem"><strong>{summary.active}</strong><span>فعال</span></div>
        <div className="kpiItem"><strong>{summary.failed}</strong><span>خطادار</span></div>
        <div className="kpiItem"><strong>{summary.inactive}</strong><span>غیرفعال</span></div>
      </div>

      <section className="panel" style={{ marginTop: 12 }}>
        <div className="panelHeader">
          <div><h2>Service inventory</h2><p>systemd units مجاز گزارش‌شده توسط Agent</p></div>
          <Link className="panelLink" href={`/services?server=${server.id}`}>فیلتر سرویس‌ها</Link>
        </div>
        <ServiceTable services={services} />
      </section>

      <section className="panel" style={{ marginTop: 12 }}>
        <div className="panelHeader"><div><h2>عملیات مدیریت‌شده</h2><p>Start، stop، restart و logs با audit کامل</p></div><Link className="panelLink" href="/operations">باز کردن عملیات</Link></div>
      </section>

      <section className="panel" style={{ marginTop: 12 }}>
        <div className="panelHeader"><div><h2>هویت Agent</h2><p>شناسه عمومی و capabilityهای این Node</p></div></div>
        <div className="panelBody identityGrid">
          <div className="identityField"><span>Public UUID</span><code>{server.id}</code></div>
          <div className="identityField"><span>Hostname</span><code>{server.hostname}</code></div>
          <div className="identityField"><span>Agent version</span><code>{server.agent_version || "—"}</code></div>
          <div className="identityField"><span>Capabilities</span><code>{server.capabilities.join(", ") || "—"}</code></div>
        </div>
      </section>
    </main>
  );
}
