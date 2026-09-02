import type { AuditEvent } from "@/lib/control-plane";
import { formatDateTime } from "@/lib/dashboard";
import { EmptyState } from "./EmptyState";

function metadataPreview(metadata: Record<string, unknown>) {
  const entries = Object.entries(metadata);
  if (entries.length === 0) return "بدون جزئیات اضافی";
  return entries
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(" · ");
}

export function AuditList({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return <EmptyState title="رویدادی ثبت نشده" description="Audit event تازه‌ای برای این محدوده وجود ندارد." />;
  }

  return (
    <div className="auditList">
      {events.map((event, index) => (
        <article className="auditRow" key={`${event.created_at}-${event.event_type}-${index}`}>
          <code className="auditType">{event.event_type}</code>
          <div className="auditMain">
            <strong dir="ltr">{event.actor}</strong>
            <span dir="ltr">{event.target_type || "control"}{event.target_id ? ` · ${event.target_id}` : ""}</span>
            <span dir="ltr">{metadataPreview(event.metadata)}</span>
          </div>
          <time className="auditTime">{formatDateTime(event.created_at)}</time>
        </article>
      ))}
    </div>
  );
}
