import Link from "next/link";
import { logoutAction } from "@/app/actions";

type NavKey = "dashboard" | "sites" | "content" | "audit" | "settings";

const items: Array<{ key: NavKey; href: string; label: string; icon: string }> = [
  { key: "dashboard", href: "/", label: "داشبورد", icon: "⌂" },
  { key: "sites", href: "/sites", label: "سایت‌ها", icon: "◎" },
  { key: "content", href: "/content", label: "مدیریت محتوا", icon: "✦" },
  { key: "audit", href: "/audit", label: "گزارش فعالیت", icon: "≋" },
  { key: "settings", href: "/settings", label: "تنظیمات و اتصال‌ها", icon: "⚙" },
];

export function AppShell({
  active,
  title,
  description,
  children,
  actions,
}: {
  active: NavKey;
  title: string;
  description?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="admin-layout">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="DigitalAfarin WordPress Agent">
          <span className="brand-logo">DA</span>
          <span>
            <strong>DigitalAfarin</strong>
            <small>WordPress Control Center</small>
          </span>
        </Link>

        <div className="nav-caption">مدیریت</div>
        <nav className="nav-list" aria-label="منوی مدیریت">
          {items.map((item) => (
            <Link className={`nav-item ${active === item.key ? "active" : ""}`} href={item.href} key={item.key}>
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="agent-badge">
            <span className="live-dot" />
            <span>
              <strong>عامل هوشمند فعال</strong>
              <small>WordPress + Search Console</small>
            </span>
          </div>
          <form action={logoutAction}><button className="nav-logout" type="submit">خروج از پنل</button></form>
        </div>
      </aside>

      <div className="workspace">
        <header className="workspace-header">
          <div className="workspace-heading">
            <p className="eyebrow">DIGITALAFARIN CONTROL CENTER</p>
            <h1>{title}</h1>
            {description && <p className="page-description">{description}</p>}
          </div>
          {actions && <div className="header-actions">{actions}</div>}
        </header>
        <main className="workspace-content">{children}</main>
      </div>
    </div>
  );
}
