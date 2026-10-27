const labels: Record<string, string> = {
  healthy: "سالم",
  attention: "نیازمند توجه",
  at_risk: "در معرض ریسک",
  critical: "بحرانی",
  active: "فعال",
  paused: "متوقف",
  archived: "آرشیو",
  todo: "برای انجام",
  doing: "در حال انجام",
  done: "انجام‌شده",
  blocked: "مسدود",
  pending: "در انتظار",
  approved: "تأییدشده",
  rejected: "ردشده",
  connected: "متصل",
  degraded: "ناپایدار",
  disconnected: "قطع",
  disabled: "غیرفعال",
  low: "کم",
  medium: "متوسط",
  high: "بالا",
};

const tone: Record<string, string> = {
  healthy: "bg-emerald-50 text-emerald-700",
  active: "bg-emerald-50 text-emerald-700",
  done: "bg-emerald-50 text-emerald-700",
  approved: "bg-emerald-50 text-emerald-700",
  connected: "bg-emerald-50 text-emerald-700",
  attention: "bg-amber-50 text-amber-700",
  pending: "bg-amber-50 text-amber-700",
  medium: "bg-amber-50 text-amber-700",
  high: "bg-orange-50 text-orange-700",
  at_risk: "bg-orange-50 text-orange-700",
  blocked: "bg-red-50 text-red-700",
  critical: "bg-red-50 text-red-700",
  rejected: "bg-red-50 text-red-700",
  degraded: "bg-orange-50 text-orange-700",
  disconnected: "bg-slate-100 text-slate-600",
  paused: "bg-slate-100 text-slate-600",
  archived: "bg-slate-100 text-slate-600",
  disabled: "bg-slate-100 text-slate-600",
  todo: "bg-sky-50 text-sky-700",
  doing: "bg-indigo-50 text-indigo-700",
  low: "bg-slate-100 text-slate-600",
};

export function StatusBadge({ value }: { value: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${tone[value] ?? "bg-slate-100 text-slate-700"}`}>
      {labels[value] ?? value}
    </span>
  );
}
