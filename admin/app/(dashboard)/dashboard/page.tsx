"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { apiGet } from "@/lib/api";
import type { DashboardSummary } from "@/lib/types";

const formatter = new Intl.NumberFormat("fa-IR");

function StatCard({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="surface-card p-5">
      <div className="text-sm font-semibold text-slate-600">{label}</div>
      <div className="mt-3 text-3xl font-black text-slate-950">{formatter.format(value)}</div>
      <div className="mt-2 text-xs text-[var(--muted)]">{hint}</div>
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    apiGet<DashboardSummary>("/api/v1/dashboard/summary")
      .then((result) => {
        if (active) setSummary(result);
      })
      .catch(() => {
        if (active) setError("دریافت وضعیت عملیاتی با خطا مواجه شد.");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="page-container">
      <PageHeader
        title="داشبورد عملیاتی"
        description="اول وضعیت را ببین؛ بعد تصمیم بگیر. این صفحه پروژه‌های فعال، کارهای بحرانی، تأییدهای منتظر و بار دپارتمان‌ها را در یک نگاه نشان می‌دهد."
      />

      {error ? <div className="surface-card mb-5 border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}

      {!summary ? (
        <div className="surface-card p-6 text-sm text-[var(--muted)]">در حال دریافت داده‌های Agency Core…</div>
      ) : (
        <div className="grid gap-5">
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="پروژه فعال" value={summary.counters.activeProjects} hint="پروژه‌های داخلی و مشتری" />
            <StatCard label="وظیفه بحرانی" value={summary.counters.criticalTasks} hint="اولویت Critical و هنوز باز" />
            <StatCard label="در انتظار تأیید" value={summary.counters.pendingApprovals} hint="اقداماتی که نیازمند تصمیم انسانی‌اند" />
            <StatCard label="وظیفه مسدود" value={summary.counters.blockedTasks} hint="نیازمند رفع مانع یا تصمیم" />
          </section>

          <section className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
            <div className="surface-card overflow-hidden">
              <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
                <div>
                  <h2 className="font-black">سلامت پروژه‌ها</h2>
                  <p className="mt-1 text-xs text-[var(--muted)]">وضعیت پروژه‌های فعال بر اساس health و priority</p>
                </div>
                <Link href="/projects" className="text-xs font-bold text-indigo-700">همه پروژه‌ها</Link>
              </div>
              <div className="divide-y divide-[var(--border)]">
                {summary.projectHealth.length ? summary.projectHealth.map((project) => (
                  <Link key={project.id} href={`/projects/${project.id}`} className="flex items-center justify-between gap-4 px-5 py-4 transition hover:bg-slate-50">
                    <div>
                      <div className="font-semibold text-slate-900">{project.name}</div>
                      <div dir="ltr" className="mt-1 text-start text-xs text-[var(--muted)]">{project.slug}</div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge value={project.priority} />
                      <StatusBadge value={project.health} />
                    </div>
                  </Link>
                )) : <div className="px-5 py-8 text-sm text-[var(--muted)]">پروژه فعالی ثبت نشده است.</div>}
              </div>
            </div>

            <div className="surface-card overflow-hidden">
              <div className="border-b border-[var(--border)] px-5 py-4">
                <h2 className="font-black">بار دپارتمان‌ها</h2>
                <p className="mt-1 text-xs text-[var(--muted)]">کارهای باز و مسدود هر واحد</p>
              </div>
              <div className="divide-y divide-[var(--border)]">
                {summary.departmentWorkload.map((department) => (
                  <Link key={department.id} href={`/departments/${department.id}`} className="flex items-center justify-between gap-4 px-5 py-4 hover:bg-slate-50">
                    <div>
                      <div className="text-sm font-semibold">{department.name}</div>
                      <div className="mt-1 text-xs text-[var(--muted)]">{formatter.format(department.openTasks)} کار باز</div>
                    </div>
                    {department.blockedTasks ? <span className="rounded-full bg-red-50 px-2.5 py-1 text-xs font-bold text-red-700">{formatter.format(department.blockedTasks)} مسدود</span> : <span className="text-xs text-emerald-700">بدون مانع</span>}
                  </Link>
                ))}
              </div>
            </div>
          </section>

          <section className="surface-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
              <div>
                <h2 className="font-black">آخرین فعالیت‌ها</h2>
                <p className="mt-1 text-xs text-[var(--muted)]">رویدادهای ثبت‌شده در Audit Log</p>
              </div>
              <Link href="/activity" className="text-xs font-bold text-indigo-700">مشاهده لاگ</Link>
            </div>
            <div className="divide-y divide-[var(--border)]">
              {summary.recentActivity.length ? summary.recentActivity.map((item) => (
                <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                  <div>
                    <div className="text-sm font-semibold text-slate-800">{item.summary}</div>
                    <div className="mt-1 text-xs text-[var(--muted)]">{item.actorLabel ?? item.actorType}</div>
                  </div>
                  <time dir="ltr" className="text-xs text-[var(--muted)]">{new Date(item.createdAt).toLocaleString("fa-IR")}</time>
                </div>
              )) : <div className="px-5 py-8 text-sm text-[var(--muted)]">فعالیتی ثبت نشده است.</div>}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
