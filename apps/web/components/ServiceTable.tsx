import type { ServiceSnapshot } from "@/lib/control-plane";
import { formatDateTime } from "@/lib/dashboard";
import { StatusBadge } from "./StatusBadge";
import { EmptyState } from "./EmptyState";

export function ServiceTable({ services, compact = false }: { services: ServiceSnapshot[]; compact?: boolean }) {
  if (services.length === 0) {
    return <EmptyState title="سرویسی پیدا نشد" description="برای این سرور هیچ سرویس allow-listed مطابق فیلتر فعلی وجود ندارد." />;
  }

  return (
    <div className={`tableWrap ${compact ? "tableCompact" : ""}`}>
      <table className="dataTable">
        <thead>
          <tr>
            <th>سرویس</th>
            <th>وضعیت</th>
            <th>Sub-state</th>
            <th>آخرین مشاهده</th>
          </tr>
        </thead>
        <tbody>
          {services.map((service) => (
            <tr key={service.unit_name}>
              <td>
                <div className="serviceIdentity">
                  <strong dir="ltr">{service.unit_name}</strong>
                  <span>{service.description || "بدون توضیح"}</span>
                </div>
              </td>
              <td><StatusBadge status={service.active_state} /></td>
              <td><code>{service.sub_state}</code></td>
              <td className="mutedCell">{formatDateTime(service.last_seen_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
