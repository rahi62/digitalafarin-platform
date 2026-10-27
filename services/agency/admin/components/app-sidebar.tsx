"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { href: "/dashboard", label: "داشبورد", icon: "⌂" },
  { href: "/projects", label: "پروژه‌ها", icon: "◫" },
  { href: "/tasks", label: "وظایف", icon: "✓" },
  { href: "/departments", label: "دپارتمان‌ها", icon: "◎" },
  { href: "/approvals", label: "تأییدها", icon: "◇" },
  { href: "/activity", label: "فعالیت‌ها", icon: "↻" },
  { href: "/integrations", label: "اتصال‌ها", icon: "⌁" },
  { href: "/settings", label: "تنظیمات", icon: "⚙" },
] as const;

export function AppSidebar({ open, onNavigate }: { open: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <aside className="app-sidebar" data-open={open} aria-label="ناوبری اصلی">
      <div className="flex h-full flex-col gap-6">
        <div className="flex items-center gap-3 px-2 py-2">
          <div className="grid size-10 place-items-center rounded-2xl bg-[var(--primary)] text-sm font-bold text-white">DA</div>
          <div>
            <div className="text-sm font-bold">دیجیتال‌آفرین</div>
            <div className="text-xs text-[var(--muted)]">Agency Control Center</div>
          </div>
        </div>

        <nav className="grid gap-1.5">
          {items.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${
                  active
                    ? "bg-[var(--primary)] font-semibold text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-950"
                }`}
              >
                <span className="grid size-7 place-items-center rounded-lg bg-black/5 text-xs" aria-hidden="true">{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto rounded-2xl border border-[var(--border)] bg-[var(--surface-soft)] p-3">
          <div className="text-xs font-semibold text-slate-700">Agency Core</div>
          <div className="mt-1 flex items-center gap-2 text-xs text-[var(--success)]">
            <span className="status-dot" />
            <span>اتصال داخلی امن</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
