import { SidebarNav } from "./SidebarNav";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="appShell">
      <aside className="sidebar">
        <div className="brandBlock">
          <div className="brandMark" aria-hidden="true">DA</div>
          <div className="brandCopy">
            <strong>DigitalAfarin</strong>
            <span>Platform</span>
          </div>
        </div>
        <SidebarNav />
        <div className="sidebarFooter">
          <span className="readOnlyDot" />
          <div>
            <strong>Control Plane</strong>
            <small>Typed Operations · Phase 2</small>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <div className="mobileBrand">
          <div className="brandMark" aria-hidden="true">DA</div>
          <div className="brandCopy"><strong>DigitalAfarin</strong><span>Platform</span></div>
        </div>
        <div className="mobileNav"><SidebarNav /></div>
        {children}
      </div>
    </div>
  );
}
