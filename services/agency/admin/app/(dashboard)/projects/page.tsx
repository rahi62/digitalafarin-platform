"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { LtrText } from "@/components/ltr-text";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { apiGet } from "@/lib/api";
import type { Project } from "@/lib/types";

const number = new Intl.NumberFormat("fa-IR");

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    apiGet<{ projects: Project[] }>("/api/v1/projects")
      .then(({ projects: rows }) => {
        if (active) setProjects(rows);
      })
      .catch(() => {
        if (active) setError("دریافت پروژه‌ها با خطا مواجه شد.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return projects;
    return projects.filter((project) => `${project.name} ${project.slug} ${project.description ?? ""}`.toLowerCase().includes(needle));
  }, [projects, query]);

  return (
    <div className="page-container">
      <PageHeader
        title="پروژه‌ها"
        description="پروژه‌های داخلی و مشتری در یک حافظه مشترک؛ تصمیم‌ها، وظایف و تاریخچه اجرا از همین موجودیت منشعب می‌شوند."
      />

      <div className="surface-card mb-5 flex flex-wrap items-center gap-3 p-4">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="جست‌وجوی نام، slug یا توضیح پروژه…"
          className="min-w-64 flex-1 rounded-xl border border-[var(--border)] bg-white px-3 py-2.5 text-sm outline-none focus:border-slate-500"
        />
        <div className="text-xs text-[var(--muted)]">{number.format(filtered.length)} پروژه</div>
      </div>

      {error ? <div className="surface-card border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}
      {loading ? <div className="surface-card p-6 text-sm text-[var(--muted)]">در حال بارگذاری پروژه‌ها…</div> : null}

      {!loading ? (
        <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
          {filtered.map((project) => (
            <Link key={project.id} href={`/projects/${project.id}`} className="surface-card group p-5 transition hover:-translate-y-0.5 hover:border-slate-300">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-black text-slate-950 group-hover:text-indigo-800">{project.name}</h2>
                  <LtrText className="mt-1 block text-xs text-[var(--muted)]">{project.slug}</LtrText>
                </div>
                <StatusBadge value={project.status} />
              </div>

              <p className="mt-4 line-clamp-3 min-h-12 text-sm leading-6 text-slate-600">{project.description || "برای این پروژه هنوز خلاصه‌ای ثبت نشده است."}</p>

              <div className="mt-5 grid grid-cols-3 gap-2 border-t border-[var(--border)] pt-4 text-center">
                <div>
                  <div className="font-black">{number.format(project.taskCount ?? project.tasks?.length ?? 0)}</div>
                  <div className="mt-1 text-[11px] text-[var(--muted)]">وظیفه</div>
                </div>
                <div>
                  <div className="font-black">{number.format(project.decisionCount ?? project.decisions?.length ?? 0)}</div>
                  <div className="mt-1 text-[11px] text-[var(--muted)]">تصمیم</div>
                </div>
                <div>
                  <div className="font-black">{number.format(project.noteCount ?? project.notes?.length ?? 0)}</div>
                  <div className="mt-1 text-[11px] text-[var(--muted)]">یادداشت</div>
                </div>
              </div>
            </Link>
          ))}
          {!filtered.length ? <div className="surface-card col-span-full p-8 text-center text-sm text-[var(--muted)]">پروژه‌ای مطابق جست‌وجو پیدا نشد.</div> : null}
        </div>
      ) : null}
    </div>
  );
}
