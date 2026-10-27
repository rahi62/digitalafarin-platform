"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { logout } from "@/lib/api";

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function handleLogout() {
    if (busy) return;
    setBusy(true);
    try {
      await logout();
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <header className="sticky top-0 z-30 border-b border-[var(--border)] bg-white/90 backdrop-blur-xl">
      <div className="page-container flex items-center justify-between !py-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onMenu}
            className="grid size-10 place-items-center rounded-xl border border-[var(--border)] bg-white text-lg lg:hidden"
            aria-label="باز کردن منو"
          >
            ☰
          </button>
          <div>
            <div className="text-sm font-bold text-slate-900">مرکز کنترل دیجیتال‌آفرین</div>
            <div className="text-xs text-[var(--muted)]">وضعیت، تصمیم، اجرا و تأیید در یک مسیر</div>
          </div>
        </div>

        <button
          type="button"
          onClick={handleLogout}
          disabled={busy}
          className="rounded-xl border border-[var(--border)] bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
        >
          {busy ? "در حال خروج…" : "خروج"}
        </button>
      </div>
    </header>
  );
}
