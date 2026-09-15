"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  label: string;
  href?: string;
  icon: string;
  disabled?: boolean;
};

const items: NavItem[] = [
  { label: "نمای کلی", href: "/", icon: "⌂" },
  { label: "سرورها", href: "/servers", icon: "▤" },
  { label: "سرویس‌ها", href: "/services", icon: "◫" },
  { label: "فعالیت‌ها", href: "/activity", icon: "◷" },
  { label: "عملیات", href: "/operations", icon: "▶" },
  { label: "استقرارها", icon: "↗", disabled: true },
  { label: "دامنه‌ها", icon: "◎", disabled: true },
  { label: "پشتیبان‌گیری", icon: "◌", disabled: true },
  { label: "تنظیمات", icon: "⚙", disabled: true },
];

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="sidebarNav" aria-label="ناوبری اصلی">
      {items.map((item) => {
        const active = item.href === "/" ? pathname === "/" : Boolean(item.href && pathname.startsWith(item.href));
        if (!item.href || item.disabled) {
          return (
            <span className="navItem navItemDisabled" key={item.label} aria-disabled="true">
              <span className="navIcon" aria-hidden="true">{item.icon}</span>
              <span>{item.label}</span>
              <small>به‌زودی</small>
            </span>
          );
        }
        return (
          <Link className={`navItem ${active ? "navItemActive" : ""}`} href={item.href} key={item.label}>
            <span className="navIcon" aria-hidden="true">{item.icon}</span>
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
