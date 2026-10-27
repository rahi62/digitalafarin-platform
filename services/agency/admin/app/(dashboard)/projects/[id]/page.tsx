"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { LtrText } from "@/components/ltr-text";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { apiGet } from "@/lib/api";
import type { Project, ProjectTask } from "@/lib/types";

type Tab = "overview" | "tasks" | "decisions" | "notes" | "kpis" | "team" | "integrations" | "activity";

const tabs: Array<{ key: Tab; label: string }> = [
  { key: "overview", label: "نمای کلی" },
  { key: "tasks", label: "وظایف" },
  { key: "decisions", label: "تصمیم‌ها" },
  { key: "notes", label: "یادداشت‌ها" },
  { key: "kpis", label: "KPI" },
  { key: "team", label: "تیم" },
  { key: "integrations", label: "اتصال‌ها" },
  { key: "activity", label: "فعالیت" },
];

export default function ProjectDetailPage() {
  const params = useParams<{ id: string | string[] }>();
  const id = Array.isArray(params.id) ? params.id[0] : params.id;
  const [project, setProject] = useState<Project | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    let active = true;
    apiGet<{ project: Project }>(`/api/v1/projects/${id}`)
      .then(({ project: row }) => {
        if (active) setProject(row);
      })
      .catch(() => {
        if (active) setError("پروژه پیدا نشد یا دریافت آن با خطا مواجه شد.");
      });
    return () => {
      active = false;
    };
  }, [id]);

  if (error) return <div className="page-container"><div className="surface-card border-red-200 bg-red-50 p-5 text-sm text-red-700">{error}</div></div>;
  if (!project) return <div className="page-container"><div className="surface-card p-6 text-sm text-[var(--muted)]">در حال خواندن حافظه پروژه…</div></div>;

  const projectTasks = (project.tasks ?? []) as ProjectTask[];

  return (
    <div className="page-container">
      <PageHeader
        title={project.name}
        description={project.description || "Context پایدار این پروژه در Agency Core"}
        actions={<StatusBadge value={project.status} />}
      />

      <div className="mb-5 flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
        <span>شناسه پروژه:</span>
        <LtrText>{project.id}</LtrText>
        <span>•</span>
        <LtrText>{project.slug}</LtrText>
      </div>

      <div className="mb-5 flex gap-2 overflow-x-auto border-b border-[var(--border)] pb-3">
        {tabs.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            className={`shrink-0 rounded-xl px-3 py-2 text-xs font-bold transition ${tab === item.key ? "bg-[var(--primary)] text-white" : "bg-white text-slate-600 hover:bg-slate-100"}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "overview" ? (
        <div className="grid gap-5 xl:grid-cols-3">
          <section className="surface-card p-5 xl:col-span-2">
            <h2 className="font-black">اهداف</h2>
            <div className="mt-4 grid gap-2">
              {project.goals.length ? project.goals.map((goal, index) => (
                <div key={`${goal}-${index}`} className="rounded-xl bg-slate-50 px-4 py-3 text-sm leading-6">{goal}</div>
              )) : <p className="text-sm text-[var(--muted)]">هدفی ثبت نشده است.</p>}
            </div>
          </section>

          <section className="surface-card p-5">
            <h2 className="font-black">Tech Stack</h2>
            <div className="mt-4 flex flex-wrap gap-2">
              {project.stack.length ? project.stack.map((item) => <LtrText key={item} className="rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs">{item}</LtrText>) : <span className="text-sm text-[var(--muted)]">ثبت نشده</span>}
            </div>
          </section>
        </div>
      ) : null}

      {tab === "tasks" ? (
        <section className="surface-card overflow-hidden">
          <div className="border-b border-[var(--border)] px-5 py-4"><h2 className="font-black">Backlog پروژه</h2></div>
          <div className="divide-y divide-[var(--border)]">
            {projectTasks.length ? projectTasks.map((task) => (
              <div key={task.id} className="flex flex-wrap items-start justify-between gap-3 px-5 py-4">
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{task.title}</div>
                  {task.details ? <p className="mt-1 text-xs leading-5 text-[var(--muted)]">{task.details}</p> : null}
                  {task.owner ? <p className="mt-2 text-xs text-slate-500">Owner: {task.owner}</p> : null}
                </div>
                <div className="flex gap-2"><StatusBadge value={task.priority} /><StatusBadge value={task.status} /></div>
              </div>
            )) : <div className="px-5 py-8 text-sm text-[var(--muted)]">وظیفه‌ای ثبت نشده است.</div>}
          </div>
        </section>
      ) : null}

      {tab === "decisions" ? (
        <section className="grid gap-3">
          {project.decisions?.length ? project.decisions.map((decision) => (
            <article key={decision.id} className="surface-card p-5">
              <h2 className="font-black">{decision.title}</h2>
              <p className="mt-3 text-sm leading-7 text-slate-700">{decision.decision}</p>
              {decision.rationale ? <p className="mt-3 border-t border-[var(--border)] pt-3 text-xs leading-6 text-[var(--muted)]">منطق تصمیم: {decision.rationale}</p> : null}
            </article>
          )) : <div className="surface-card p-6 text-sm text-[var(--muted)]">تصمیمی ثبت نشده است.</div>}
        </section>
      ) : null}

      {tab === "notes" ? (
        <section className="grid gap-3">
          {project.notes?.length ? project.notes.map((note) => (
            <article key={note.id} className="surface-card p-5 text-sm leading-7 text-slate-700">
              {note.text}
              <time dir="ltr" className="mt-3 block text-xs text-[var(--muted)]">{new Date(note.createdAt).toLocaleString("fa-IR")}</time>
            </article>
          )) : <div className="surface-card p-6 text-sm text-[var(--muted)]">یادداشتی ثبت نشده است.</div>}
        </section>
      ) : null}

      {tab === "kpis" || tab === "team" || tab === "integrations" || tab === "activity" ? (
        <section className="surface-card p-6">
          <h2 className="font-black">{tabs.find((item) => item.key === tab)?.label}</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">این نمای پروژه در v1 از Registry مرکزی Agency تغذیه می‌شود و در فاز عملیاتی بعدی با داده‌های اختصاصی همین پروژه تکمیل می‌شود.</p>
        </section>
      ) : null}
    </div>
  );
}
