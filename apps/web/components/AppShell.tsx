import Link from "next/link";
import { SidebarNav } from "./SidebarNav";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="railShell">
      <aside className="railSidebar">
        <Link href="/projects" className="railBrand">
          <span className="railBrandMark">DA</span>
          <span>
            <strong>DigitalAfarin</strong>
            <small>Platform</small>
          </span>
        </Link>

        <SidebarNav />

        <div className="railSidebarFooter">
          <span className="railStatusDot" />
          <span>
            <strong>Production</strong>
            <small>Control Plane online</small>
          </span>
        </div>
      </aside>

      <div className="railWorkspace">
        <header className="railMobileHeader">
          <Link href="/projects" className="railBrand">
            <span className="railBrandMark">DA</span>
            <span>
              <strong>DigitalAfarin</strong>
              <small>Platform</small>
            </span>
          </Link>
        </header>
        <div className="railMobileNav"><SidebarNav /></div>
        {children}
      </div>
    </div>
  );
}
