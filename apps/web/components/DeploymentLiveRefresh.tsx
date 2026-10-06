"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function DeploymentLiveRefresh({ active }: { active: boolean }) {
  const router = useRouter();

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => router.refresh(), 2500);
    return () => window.clearInterval(timer);
  }, [active, router]);

  if (!active) return null;

  return (
    <span className="deployLiveBadge" aria-live="polite">
      <i />
      Live
    </span>
  );
}
