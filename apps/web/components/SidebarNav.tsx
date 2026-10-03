"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Item = { href: string; label: string; icon: string };

const primary: Item[] = [
  { href: "/projects", label: "Projects", icon: "◫" },
  { href: "/activity", label: "Observability", icon: "⌁" },
  { href: "/settings", label: "Settings", icon: "⚙" },
];

const advanced: Item[] = [
  { href: "/servers", label: "Infrastructure", icon: "▤" },
  { href: "/operations", label: "Operations", icon: "↗" },
  { href: "/services", label: "All services", icon: "◎" },
];

function NavLink({ item, pathname }: { item: Item; pathname: string }) {
  const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
  return (
    <Link className={`railNavItem ${active ? "railNavItemActive" : ""}`} href={item.href}>
      <span className="railNavIcon" aria-hidden="true">{item.icon}</span>
      <span>{item.label}</span>
    </Link>
  );
}

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="railNav" aria-label="ناوبری اصلی">
      <div className="railNavGroup">
        {primary.map((item) => <NavLink key={item.href} item={item} pathname={pathname} />)}
      </div>

      <details className="railAdvanced" open={advanced.some((item) => pathname.startsWith(item.href))}>
        <summary>Advanced</summary>
        <div className="railNavGroup">
          {advanced.map((item) => <NavLink key={item.href} item={item} pathname={pathname} />)}
        </div>
      </details>
    </nav>
  );
}
