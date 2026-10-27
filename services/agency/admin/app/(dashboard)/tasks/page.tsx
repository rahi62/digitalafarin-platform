"use client";

import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { AgencyApiError, apiGet, apiMutation } from "@/lib/api";
import type { Task, TaskStatus } from "@/lib/types";

const statusOptions: Array<{ value: "all" | TaskStatus; label: string }> = [
  { value: "all", label: "همه وضعیت‌ها" },
  { value: "todo", label: "برای انجام" },
  { value: "doing", label: "در حال انجام" },
  { value: "blocked", label: "مسدود" },
  { value: "done", label: "انجام‌شده" },
];

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | TaskStatus>("all");
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    try {
      const { tasks: rows } = await apiGet<{ tasks: Task[] }>("/api/v1/tasks");
      setTasks(rows);
      setError("");
    } catch {
      setError("دریافت Backlog با خطا مواجه شد.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return tasks.filter((task) => {
      if (status !== "all" && task.status !== status) return false;
      if (!needle) return true;
      return `${task.title} ${task.description ?? ""} ${task.ownerLabel ?? ""} ${task.executorType}`.toLowerCase().includes(needle);
    });
  }, [tasks, query, status]);

  async function updateStatus(task: Task, nextStatus: TaskStatus) {
    setBusyId(task.id);
    setError("");
    try {
      const { task: updated } = await apiMutation<{ task: Task }>(`/api/v1/tasks/${task.id}`, "PATCH", { status: nextStatus });
      setTasks((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (cause) {
      setError(cause instanceof AgencyApiError ? cause.message : "به‌روزرسانی وظیفه انجام نشد.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="page-container">
      <PageHeader
        title="وظایف"
        description="Backlog سراسری Agency؛ هر وظیفه باید پروژه، ریسک، اولویت، Owner و Executor مشخص داشته باشد."
      />

      <div className="surface-card mb-5 grid gap-3 p-4 md:grid-cols-[1fr_auto]">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="جست‌وجوی وظیفه، Owner یا Executor…"
          className="rounded-xl border border-[var(--border)] bg-white px-3 py-2.5 text-sm outline-none focus:border-slate-500"
        />
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as "all" | TaskStatus)}
          className="rounded-xl border border-[var(--border)] bg-white px-3 py-2.5 text-sm outline-none"
        >
          {statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </div>

      {error ? <div className="surface-card mb-5 border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-3">
        {filtered.map((task) => (
          <article key={task.id} className="surface-card p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-black text-slate-950">{task.title}</h2>
                  {task.approvalRequired ? <span className="rounded-full bg-purple-50 px-2.5 py-1 text-[11px] font-bold text-purple-700">نیازمند تأیید</span> : null}
                </div>
                {task.description ? <p className="mt-2 text-sm leading-6 text-slate-600">{task.description}</p> : null}
                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-[var(--muted)]">
                  <span>Owner: {task.ownerLabel || "تعیین نشده"}</span>
                  <span dir="ltr">Executor: {task.executorType}</span>
                  {task.dueDate ? <span>موعد: {new Date(`${task.dueDate}T00:00:00`).toLocaleDateString("fa-IR")}</span> : null}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge value={task.riskLevel} />
                <StatusBadge value={task.priority} />
                <StatusBadge value={task.status} />
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[var(--border)] pt-4">
              <span className="text-xs font-semibold text-slate-500">تغییر وضعیت:</span>
              {(["todo", "doing", "blocked", "done"] as TaskStatus[]).map((nextStatus) => (
                <button
                  key={nextStatus}
                  type="button"
                  disabled={busyId === task.id || task.status === nextStatus}
                  onClick={() => updateStatus(task, nextStatus)}
                  className="rounded-lg border border-[var(--border)] bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {statusOptions.find((option) => option.value === nextStatus)?.label}
                </button>
              ))}
            </div>
          </article>
        ))}
        {!filtered.length ? <div className="surface-card p-8 text-center text-sm text-[var(--muted)]">وظیفه‌ای مطابق فیلتر فعلی نیست.</div> : null}
      </div>
    </div>
  );
}
