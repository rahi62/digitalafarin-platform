"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AgencyApiError, apiGet } from "@/lib/api";
import type { CurrentUser } from "@/lib/types";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    apiGet<{ user: CurrentUser; permissions: string[] }>("/api/v1/auth/me")
      .then(() => {
        if (active) setReady(true);
      })
      .catch((error) => {
        if (!active) return;
        if (error instanceof AgencyApiError && error.status === 401) {
          router.replace("/login");
          return;
        }
        setReady(true);
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (!ready) {
    return (
      <div className="grid min-h-screen place-items-center bg-[var(--background)]">
        <div className="surface-card flex items-center gap-3 px-5 py-4 text-sm text-slate-600">
          <span className="size-2 animate-pulse rounded-full bg-[var(--primary)]" />
          در حال بررسی نشست امن…
        </div>
      </div>
    );
  }

  return children;
}
