import { statusTone } from "@/lib/dashboard";

const labels: Record<string, string> = {
  online: "آنلاین",
  stale: "داده قدیمی",
  offline: "آفلاین",
  active: "فعال",
  failed: "خطا",
  inactive: "غیرفعال",
  running: "در حال اجرا",
  dead: "متوقف",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`statusBadge status-${statusTone(status)}`}>
      <span className="statusIndicator" />
      {labels[status] ?? status}
    </span>
  );
}
