"use client";

import { useEffect, useTransition } from "react";
import { useRouter } from "next/navigation";

export function OperationRefresh({ active }: { active: boolean }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => {
      if (document.visibilityState === "visible" && !pending) {
        startTransition(() => router.refresh());
      }
    }, 4000);
    return () => clearInterval(timer);
  }, [active, pending, router]);
  return active ? <span role="status" className="railMuted">بروزرسانی خودکار وضعیت</span> : null;
}
