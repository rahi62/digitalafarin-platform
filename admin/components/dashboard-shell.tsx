"use client";

import { useState } from "react";
import { AppSidebar } from "./app-sidebar";
import { Topbar } from "./topbar";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="app-shell">
      {menuOpen ? (
        <button
          type="button"
          aria-label="بستن منو"
          onClick={() => setMenuOpen(false)}
          className="fixed inset-0 z-40 bg-slate-950/30 backdrop-blur-[1px] lg:hidden"
        />
      ) : null}
      <AppSidebar open={menuOpen} onNavigate={() => setMenuOpen(false)} />
      <div className="app-main">
        <Topbar onMenu={() => setMenuOpen(true)} />
        <main>{children}</main>
      </div>
    </div>
  );
}
