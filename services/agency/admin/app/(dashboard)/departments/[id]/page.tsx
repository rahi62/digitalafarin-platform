"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { LtrText } from "@/components/ltr-text";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { apiGet } from "@/lib/api";
import type { Department, Task } from "@/lib/types";

type DepartmentRole = {
  id: string;
  slug: string;
  name: string;
  mission?: string | null;
  responsibilities?: string[] | null;
};

type WorkflowStep = { id: string; position: number; name: string; stepType: string; config: Record<string, unknown> };
type Workflow = { id: string; slug: string; name: string; description?: string | null; status: string; steps?: WorkflowStep[] };

export default function DepartmentDetailPage() {
  const params = useParams<{ id: string | string[] }>();
  const id = Array.isArray(params.id) ? params.id[0] : params.id;
  const [department, setDepartment] = useState<Department | null>(null);
  const [roles, setRoles] = useState<DepartmentRole[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    let active = true;
    Promise.all([
      apiGet<{ department: Department; roles: DepartmentRole[]; tasks: Task[]; workflows: Workflow[] }>(`/api/v1/departments/${id}`),
      apiGet<{ workflows: Workflow[] }>(`/api/v1/departments/${id}/workflows`),
    ])
      .then(([detail, workflowDetail]) => {
        if (!active) return;
        setDepartment(detail.department);
        setRoles(detail.roles);
        setTasks(detail.tasks);
        setWorkflows(workflowDetail.workflows);
      })
      .catch(() => {
        if (active) setError("خواندن دپارتمان با خطا مواجه شد.");
      });
    return () => {
      active = false;
    };
  }, [id]);

  if (error) return <div className="page-container"><div className="surface-card border-red-200 bg-red-50 p-5 text-sm text-red-700">{error}</div></div>;
  if (!department) return <div className="page-container"><div className="surface-card p-6 text-sm text-[var(--muted)]">در حال بارگذاری دپارتمان…</div></div>;

  return (
    <div className="page-container">
      <PageHeader title={department.name} description={department.mission ?? undefined} actions={<StatusBadge value={department.status} />} />
      <LtrText className="mb-5 block text-xs text-[var(--muted)]">{department.slug}</LtrText>

      <div className="grid gap-5 2xl:grid-cols-[1fr_1.1fr]">
        <section className="surface-card overflow-hidden">
          <div className="border-b border-[var(--border)] px-5 py-4">
            <h2 className="font-black">Roleها و Capabilityها</h2>
            <p className="mt-1 text-xs text-[var(--muted)]">در v1 این Roleها می‌توانند Human-led یا Virtual/AI-assisted باشند.</p>
          </div>
          <div className="divide-y divide-[var(--border)]">
            {roles.map((role) => (
              <article key={role.id} className="px-5 py-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-black">{role.name}</h3>
                  <LtrText className="text-[11px] text-[var(--muted)]">{role.slug}</LtrText>
                </div>
                {role.mission ? <p className="mt-2 text-xs leading-6 text-slate-600">{role.mission}</p> : null}
                {role.responsibilities?.length ? (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {role.responsibilities.map((item) => <span key={item} className="rounded-lg bg-slate-100 px-2 py-1 text-[11px] text-slate-600">{item}</span>)}
                  </div>
                ) : null}
              </article>
            ))}
            {!roles.length ? <div className="px-5 py-8 text-sm text-[var(--muted)]">Role تخصصی برای این دپارتمان ثبت نشده است.</div> : null}
          </div>
        </section>

        <div className="grid content-start gap-5">
          {workflows.map((workflow) => (
            <section key={workflow.id} className="surface-card overflow-hidden">
              <div className="border-b border-[var(--border)] px-5 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="font-black">{workflow.name}</h2>
                    <LtrText className="mt-1 block text-[11px] text-[var(--muted)]">{workflow.slug}</LtrText>
                  </div>
                  <StatusBadge value={workflow.status} />
                </div>
                {workflow.description ? <p className="mt-3 text-xs leading-6 text-slate-600">{workflow.description}</p> : null}
              </div>
              <ol className="divide-y divide-[var(--border)]">
                {workflow.steps?.map((step) => (
                  <li key={step.id} className="flex gap-3 px-5 py-4">
                    <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-[var(--primary-soft)] text-xs font-black text-indigo-800">{step.position}</span>
                    <div>
                      <div className="text-sm font-black">{step.name}</div>
                      <div className="mt-1 text-[11px] text-[var(--muted)]">{step.stepType}</div>
                      {typeof step.config.outcome === "string" ? <p className="mt-2 text-xs leading-6 text-slate-600">{step.config.outcome}</p> : null}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          ))}

          <section className="surface-card p-5">
            <h2 className="font-black">Workload</h2>
            <div className="mt-4 grid grid-cols-3 gap-3 text-center">
              <div className="rounded-xl bg-slate-50 p-3"><div className="text-xl font-black">{new Intl.NumberFormat("fa-IR").format(tasks.length)}</div><div className="mt-1 text-[11px] text-[var(--muted)]">کل وظایف</div></div>
              <div className="rounded-xl bg-amber-50 p-3"><div className="text-xl font-black text-amber-800">{new Intl.NumberFormat("fa-IR").format(tasks.filter((task) => task.status === "doing").length)}</div><div className="mt-1 text-[11px] text-amber-700">در حال انجام</div></div>
              <div className="rounded-xl bg-red-50 p-3"><div className="text-xl font-black text-red-800">{new Intl.NumberFormat("fa-IR").format(tasks.filter((task) => task.status === "blocked").length)}</div><div className="mt-1 text-[11px] text-red-700">مسدود</div></div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
