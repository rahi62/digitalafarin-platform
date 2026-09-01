"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function SyncButton() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function sync() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/sync", { method: "POST" });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail ?? "Sync failed");
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="syncWrap">
      <button className="primaryButton" onClick={sync} disabled={loading}>
        {loading ? "در حال همگام‌سازی…" : "Sync server"}
      </button>
      {error ? <span className="errorText">{error}</span> : null}
    </div>
  );
}
