export type StatusTone = "success" | "warning" | "danger" | "neutral";

type ServiceState = {
  active_state: string;
};

const faNumber = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });

export function formatUptime(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds || 0));
  const days = Math.floor(safe / 86400);
  const hours = Math.floor((safe % 86400) / 3600);
  const minutes = Math.floor((safe % 3600) / 60);

  if (days > 0) return `${faNumber.format(days)} روز و ${faNumber.format(hours)} ساعت`;
  if (hours > 0) return `${faNumber.format(hours)} ساعت و ${faNumber.format(minutes)} دقیقه`;
  return `${faNumber.format(minutes)} دقیقه`;
}

export function formatAge(ageSeconds: number | null | undefined): string {
  if (ageSeconds === null || ageSeconds === undefined) return "بدون داده";
  const age = Math.max(0, Math.floor(ageSeconds));
  if (age < 60) return `${faNumber.format(age)} ثانیه پیش`;
  if (age < 3600) return `${faNumber.format(Math.floor(age / 60))} دقیقه پیش`;
  if (age < 86400) return `${faNumber.format(Math.floor(age / 3600))} ساعت پیش`;
  return `${faNumber.format(Math.floor(age / 86400))} روز پیش`;
}

export function summarizeServices(services: ServiceState[]) {
  const active = services.filter((service) => service.active_state === "active").length;
  const failed = services.filter((service) => service.active_state === "failed").length;
  const inactive = services.filter((service) => service.active_state === "inactive").length;
  return {
    total: services.length,
    active,
    failed,
    inactive,
    unhealthy: services.length - active,
  };
}

export function statusTone(status: string): StatusTone {
  switch (status) {
    case "online":
    case "active":
    case "running":
      return "success";
    case "stale":
    case "inactive":
    case "dead":
      return "warning";
    case "offline":
    case "failed":
      return "danger";
    default:
      return "neutral";
  }
}

export function formatPercent(value: number): string {
  return `${new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 }).format(value)}٪`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("fa-IR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
