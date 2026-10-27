"use client";

import { useEffect, useState } from "react";
import { LtrText } from "@/components/ltr-text";
import { PageHeader } from "@/components/page-header";
import { apiGet } from "@/lib/api";
import type { Activity } from "@/lib/types";

const actorLabels: Record<string, string> = {
  user: "کاربر",
  chatgpt: "ChatGPT",
  system: "سیستم",
  integration: "Integration",
};

export default function ActivityPage() {
  const [activity, setActivity] = useState<Activity[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    apiGet<{ activity: Activity[] }>("/api/v1/activity?limit=200")
      .then(({ activity: rows }) => {
        if (active) setActivity(rows);
      })
      .catch(() => {
        if (active) setError("خواندن Activity Log با خطا مواجه شد.");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="page-container">
      <PageHeader
        title="فعالیت‌ها"
        description="Audit Log فقط‌افزودنی Agency؛ چه کسی، چه چیزی و چه زمانی تغییر داده یا اجرا کرده است."
      />

      {error ? <div className="surface-card mb-5 border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}

      <section className="surface-card overflow-hidden">
        <div className="divide-y divide-[var(--border)]">
          {activity.map((item) => (
            <article key={item.id} className="grid gap-3 px-5 py-4 lg:grid-cols-[1fr_auto] lg:items-center">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-lg bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-600">{actorLabels[item.actorType] ?? item.actorType}</span>
                  <h2 className="text-sm font-semibold text-slate-800">{item.summary}</h2>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
                  <span>{item.actorLabel || "بدون نام"}</span>
                  <span>•</span>
                  <LtrText>{item.action}</LtrText>
                  {item.entityId ? <><span>•</span><LtrText>{item.entityId}</LtrText></> : null}
                </div>
              </div>
              <time dir="ltr" className="text-xs text-[var(--muted)]">{new Date(item.createdAt).toLocaleString("fa-IR")}</time>
            </article>
          ))}
          {!activity.length && !error ? <div className="px-5 py-8 text-center text-sm text-[var(--muted)]">هنوز Activity ثبت نشده است.</div> : null}
        </div>
      </section>
    </div>
  );
}
