import Link from "next/link";
import { AuditList } from "@/components/AuditList";
import { EmptyState } from "@/components/EmptyState";
import { MetricCard } from "@/components/MetricCard";
import { ServiceTable } from "@/components/ServiceTable";
import { StatusBadge } from "@/components/StatusBadge";
import {
  ControlPlaneError,
  getMetrics,
  getServer,
  listAuditEvents,
  listServers,
  listServices,
} from "@/lib/control-plane";
import { formatAge, formatPercent, formatUptime, summarizeServices } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

function metricState(value: number, warning: number, danger: number): "normal" | "warning" | "danger" {
  if (value >= danger) return "danger";
  if (value >= warning) return "warning";
  return "normal";
}

export default async function Home() {
  const [serversResult, serverResult, metricsResult, servicesResult, auditResult] = await Promise.allSettled([
    listServers(),
    getServer("default"),
    getMetrics("default"),
    listServices("default"),
    listAuditEvents({ limit: 8 }),
  ]);

  const servers = serversResult.status === "fulfilled" ? serversResult.value : [];
  const server = serverResult.status === "fulfilled" ? serverResult.value : null;
  const metrics = metricsResult.status === "fulfilled" ? metricsResult.value : null;
  const services = servicesResult.status === "fulfilled" ? servicesResult.value : [];
  const audits = auditResult.status === "fulfilled" ? auditResult.value : [];
  const serviceSummary = summarizeServices(services);
  const unhealthy = services.filter((service) => service.active_state !== "active");
  const onlineServers = servers.filter((item) => item.status === "online").length;

  const metricsError = metricsResult.status === "rejected" && metricsResult.reason instanceof ControlPlaneError
    ? metricsResult.reason
    : null;

  return (
    <main className="page">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">INFRASTRUCTURE OVERVIEW</p>
          <h1>نمای کلی زیرساخت</h1>
          <p className="pageLead">
            وضعیت زنده سرورها، منابع سیستم و سرویس‌های allow-listed از Control Plane مرکزی.
          </p>
        </div>
        {server ? (
          <div className="pageActions">
            <StatusBadge status={server.status} />
          </div>
        ) : null}
      </header>

      {!server ? (
        <section className="panel errorPanel">
          <EmptyState
            title="Control Plane در دسترس نیست"
            description="سرور پیش‌فرض از API خوانده نشد. اتصال و Service Principal پنل را بررسی کنید."
          />
        </section>
      ) : (
        <>
          {server.status !== "online" ? (
            <div className="notice">
              آخرین heartbeat این سرور {formatAge(server.age_seconds)} ثبت شده و وضعیت فعلی «{server.status}» است.
            </div>
          ) : null}

          <div className="metricsGrid">
            <MetricCard
              label="CPU"
              value={metrics ? formatPercent(metrics.cpu_percent) : "—"}
              level={metrics?.cpu_percent}
              state={metrics ? metricState(metrics.cpu_percent, 70, 90) : "warning"}
              hint={metrics ? `نمونه ${formatAge(metrics.age_seconds)}` : metricsError?.message ?? "داده در دسترس نیست"}
            />
            <MetricCard
              label="RAM"
              value={metrics ? formatPercent(metrics.memory_percent) : "—"}
              level={metrics?.memory_percent}
              state={metrics ? metricState(metrics.memory_percent, 75, 90) : "warning"}
              hint={metrics ? `Agent ${server.agent_version || "—"}` : "Metrics unavailable"}
            />
            <MetricCard
              label="Disk"
              value={metrics ? formatPercent(metrics.disk_percent) : "—"}
              level={metrics?.disk_percent}
              state={metrics ? metricState(metrics.disk_percent, 75, 90) : "warning"}
              hint={metrics ? "پارتیشن اصلی سرور" : "Metrics unavailable"}
            />
            <MetricCard
              label="Uptime"
              value={metrics ? formatUptime(metrics.uptime_seconds) : "—"}
              hint={server.hostname || "بدون hostname"}
            />
          </div>

          <div className="kpiStrip" style={{ marginTop: 12 }}>
            <div className="kpiItem"><strong>{servers.length}</strong><span>کل سرورها</span></div>
            <div className="kpiItem"><strong>{onlineServers}</strong><span>سرور آنلاین</span></div>
            <div className="kpiItem"><strong>{serviceSummary.active}</strong><span>سرویس فعال</span></div>
            <div className="kpiItem"><strong>{serviceSummary.failed}</strong><span>سرویس خطادار</span></div>
          </div>

          <div className="sectionGrid">
            <section className="panel">
              <div className="panelHeader">
                <div><h2>سرویس‌های نیازمند توجه</h2><p>{serviceSummary.total} سرویس روی {server.name} مشاهده شده است.</p></div>
                <Link className="panelLink" href="/services">همه سرویس‌ها</Link>
              </div>
              {unhealthy.length > 0 ? (
                <ServiceTable services={unhealthy.slice(0, 6)} compact />
              ) : (
                <EmptyState title="همه سرویس‌ها سالم‌اند" description="در snapshot فعلی هیچ سرویس inactive یا failed وجود ندارد." />
              )}
            </section>

            <section className="panel">
              <div className="panelHeader">
                <div><h2>سرور پیش‌فرض</h2><p>Identity و freshness فعلی Agent</p></div>
                <Link className="panelLink" href={`/servers/${server.id}`}>جزئیات</Link>
              </div>
              <div className="panelBody">
                <div className="serverCardTop">
                  <div className="serverIdentity">
                    <strong>{server.name}</strong>
                    <code>{server.hostname}</code>
                  </div>
                  <StatusBadge status={server.status} />
                </div>
                <div className="serverMeta" style={{ marginTop: 20 }}>
                  <div className="metaCell"><span>Heartbeat</span><strong>{formatAge(server.age_seconds)}</strong></div>
                  <div className="metaCell"><span>Agent</span><strong dir="ltr">v{server.agent_version || "—"}</strong></div>
                  <div className="metaCell"><span>Capabilities</span><strong>{server.capabilities.length}</strong></div>
                  <div className="metaCell"><span>UUID</span><strong dir="ltr">{server.id.slice(0, 8)}…</strong></div>
                </div>
              </div>
            </section>
          </div>

          <section className="panel" style={{ marginTop: 12 }}>
            <div className="panelHeader">
              <div><h2>آخرین فعالیت‌ها</h2><p>Audit trail مربوط به MCP، Agent و Control Plane</p></div>
              <Link className="panelLink" href="/activity">مشاهده کامل</Link>
            </div>
            <AuditList events={audits} />
          </section>
        </>
      )}
    </main>
  );
}
