"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LtrText } from "@/components/ltr-text";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { apiGet } from "@/lib/api";
import type { Department } from "@/lib/types";

export default function DepartmentsPage() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    apiGet<{ departments: Department[] }>("/api/v1/departments")
      .then(({ departments: rows }) => {
        if (active) setDepartments(rows);
      })
      .catch(() => {
        if (active) setError("دریافت دپارتمان‌ها با خطا مواجه شد.");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="page-container">
      <PageHeader
        title="دپارتمان‌ها"
        description="ساختار سازمانی واقعی Agency؛ Roleها و Workflowها یک‌بار تعریف می‌شوند و پروژه‌ها به ظرفیت مناسب متصل می‌شوند."
      />

      {error ? <div className="surface-card mb-5 border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
        {departments.map((department) => (
          <Link key={department.id} href={`/departments/${department.id}`} className="surface-card group p-5 transition hover:-translate-y-0.5 hover:border-slate-300">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-black group-hover:text-indigo-800">{department.name}</h2>
                <LtrText className="mt-1 block text-xs text-[var(--muted)]">{department.slug}</LtrText>
              </div>
              <StatusBadge value={department.status} />
            </div>
            <p className="mt-4 min-h-16 text-sm leading-7 text-slate-600">{department.mission || "Mission این دپارتمان هنوز ثبت نشده است."}</p>
            <div className="mt-5 border-t border-[var(--border)] pt-4 text-xs font-semibold text-slate-500">مشاهده Roleها، Workflowها و Backlog ←</div>
          </Link>
        ))}
        {!departments.length && !error ? <div className="surface-card col-span-full p-8 text-center text-sm text-[var(--muted)]">در حال خواندن ساختار سازمانی…</div> : null}
      </div>
    </div>
  );
}
