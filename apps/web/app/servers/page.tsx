import Link from "next/link";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";
import { listServers } from "@/lib/control-plane";
import { formatAge } from "@/lib/dashboard";

export const dynamic = "force-dynamic";

export default async function ServersPage() {
  let servers;
  try {
    servers = await listServers();
  } catch {
    servers = [];
  }

  return (
    <main className="page">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">SERVER FLEET</p>
          <h1>سرورها</h1>
          <p className="pageLead">وضعیت و هویت تمام Agentهای ثبت‌شده در Control Plane.</p>
        </div>
      </header>

      {servers.length === 0 ? (
        <section className="panel errorPanel">
          <EmptyState title="سروری پیدا نشد" description="Control Plane هیچ Server فعال قابل مشاهده‌ای برای این Service Principal برنگرداند." />
        </section>
      ) : (
        <div className="serverCards">
          {servers.map((server) => (
            <Link className="serverCard" href={`/servers/${server.id}`} key={server.id}>
              <div className="serverCardTop">
                <div className="serverIdentity">
                  <strong>{server.name}</strong>
                  <code>{server.hostname}</code>
                </div>
                <StatusBadge status={server.status} />
              </div>
              <div className="serverMeta">
                <div className="metaCell"><span>Heartbeat</span><strong>{formatAge(server.age_seconds)}</strong></div>
                <div className="metaCell"><span>Agent</span><strong dir="ltr">v{server.agent_version || "—"}</strong></div>
                <div className="metaCell"><span>Default</span><strong>{server.is_default ? "بله" : "خیر"}</strong></div>
                <div className="metaCell"><span>Capabilities</span><strong>{server.capabilities.length}</strong></div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
