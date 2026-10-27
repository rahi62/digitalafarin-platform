"use client";

import { useEffect, useMemo, useState } from "react";
import { LtrText } from "@/components/ltr-text";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { AgencyApiError, apiGet, apiMutation } from "@/lib/api";
import type { Approval } from "@/lib/types";

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [filter, setFilter] = useState<"pending" | "all">("pending");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      const { approvals: rows } = await apiGet<{ approvals: Approval[] }>("/api/v1/approvals");
      setApprovals(rows);
      setError("");
    } catch {
      setError("دریافت صف تأیید با خطا مواجه شد.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const visible = useMemo(() => filter === "pending" ? approvals.filter((item) => item.status === "pending") : approvals, [approvals, filter]);

  async function approve(id: string) {
    setBusyId(id);
    setError("");
    try {
      await apiMutation(`/api/v1/approvals/${id}/approve`, "POST", {});
      await load();
    } catch (cause) {
      setError(cause instanceof AgencyApiError ? cause.message : "تأیید عملیات انجام نشد.");
    } finally {
      setBusyId(null);
    }
  }

  async function reject(id: string) {
    const reason = window.prompt("دلیل رد این عملیات را ثبت کنید:")?.trim();
    if (!reason) return;
    setBusyId(id);
    setError("");
    try {
      await apiMutation(`/api/v1/approvals/${id}/reject`, "POST", { reason });
      await load();
    } catch (cause) {
      setError(cause instanceof AgencyApiError ? cause.message : "رد عملیات انجام نشد.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="page-container">
      <PageHeader
        title="تأییدها"
        description="نقطه کنترل انسانی Agency. عملیات حساس تا زمانی که اینجا تأیید نشوند وارد Execution Queue نمی‌شوند."
        actions={
          <div className="flex rounded-xl border border-[var(--border)] bg-white p-1">
            <button type="button" onClick={() => setFilter("pending")} className={`rounded-lg px-3 py-1.5 text-xs font-bold ${filter === "pending" ? "bg-[var(--primary)] text-white" : "text-slate-600"}`}>در انتظار</button>
            <button type="button" onClick={() => setFilter("all")} className={`rounded-lg px-3 py-1.5 text-xs font-bold ${filter === "all" ? "bg-[var(--primary)] text-white" : "text-slate-600"}`}>همه</button>
          </div>
        }
      />

      {error ? <div className="surface-card mb-5 border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-4">
        {visible.map((approval) => (
          <article key={approval.id} className="surface-card overflow-hidden">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--border)] px-5 py-4">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-black">{approval.actionType}</h2>
                  <StatusBadge value={approval.riskLevel} />
                  <StatusBadge value={approval.status} />
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
                  <span>Project:</span><LtrText>{approval.projectId}</LtrText>
                  {approval.taskId ? <><span>• Task:</span><LtrText>{approval.taskId}</LtrText></> : null}
                </div>
              </div>
              <time dir="ltr" className="text-xs text-[var(--muted)]">{new Date(approval.requestedAt).toLocaleString("fa-IR")}</time>
            </div>

            <div className="grid gap-4 p-5 xl:grid-cols-2">
              <div>
                <h3 className="text-xs font-black text-slate-500">Payload پیشنهادی</h3>
                <pre dir="ltr" className="mt-2 max-h-72 overflow-auto rounded-xl bg-slate-950 p-4 text-start text-[11px] leading-5 text-slate-100">{JSON.stringify(approval.payload, null, 2)}</pre>
              </div>
              <div>
                <h3 className="text-xs font-black text-slate-500">Diff / Preview</h3>
                <pre dir="ltr" className="mt-2 max-h-72 overflow-auto rounded-xl bg-slate-100 p-4 text-start text-[11px] leading-5 text-slate-700">{JSON.stringify(approval.diffPreview ?? {}, null, 2)}</pre>
              </div>
            </div>

            {approval.status === "pending" ? (
              <div className="flex flex-wrap justify-end gap-2 border-t border-[var(--border)] bg-slate-50 px-5 py-4">
                <button type="button" disabled={busyId === approval.id} onClick={() => reject(approval.id)} className="rounded-xl border border-red-200 bg-white px-4 py-2 text-xs font-black text-red-700 disabled:opacity-50">رد عملیات</button>
                <button type="button" disabled={busyId === approval.id} onClick={() => approve(approval.id)} className="rounded-xl bg-[var(--primary)] px-4 py-2 text-xs font-black text-white disabled:opacity-50">تأیید عملیات</button>
              </div>
            ) : approval.reason ? <div className="border-t border-[var(--border)] px-5 py-3 text-xs text-[var(--muted)]">دلیل/یادداشت: {approval.reason}</div> : null}
          </article>
        ))}

        {!visible.length ? <div className="surface-card p-8 text-center text-sm text-[var(--muted)]">هیچ عملیات منتظر تأییدی وجود ندارد.</div> : null}
      </div>
    </div>
  );
}
