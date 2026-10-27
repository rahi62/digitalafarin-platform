"use client";

import { useEffect, useState } from "react";
import { LtrText } from "@/components/ltr-text";
import { PageHeader } from "@/components/page-header";
import { apiGet } from "@/lib/api";
import type { CurrentUser } from "@/lib/types";

export default function SettingsPage() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    apiGet<{ user: CurrentUser; permissions: string[] }>("/api/v1/auth/me")
      .then((result) => {
        if (!active) return;
        setUser(result.user);
        setPermissions(result.permissions.sort());
      })
      .catch(() => {
        if (active) setError("خواندن تنظیمات دسترسی با خطا مواجه شد.");
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="page-container">
      <PageHeader
        title="تنظیمات"
        description="هویت، Permissionها و Policyهای امنیتی پنل. اعمال Permission در Backend انجام می‌شود، نه صرفاً در رابط کاربری."
      />

      {error ? <div className="surface-card mb-5 border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}

      <div className="grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
        <section className="surface-card p-5">
          <h2 className="font-black">کاربر فعلی</h2>
          {user ? (
            <div className="mt-4 grid gap-3 text-sm">
              <div className="rounded-xl bg-slate-50 p-3"><div className="text-xs text-[var(--muted)]">نام</div><div className="mt-1 font-semibold">{user.displayName}</div></div>
              <div className="rounded-xl bg-slate-50 p-3"><div className="text-xs text-[var(--muted)]">ایمیل</div><LtrText className="mt-1 block text-sm">{user.email}</LtrText></div>
              <div className="rounded-xl bg-slate-50 p-3"><div className="text-xs text-[var(--muted)]">شناسه</div><LtrText className="mt-1 block break-all text-xs">{user.userId ?? user.id ?? "—"}</LtrText></div>
            </div>
          ) : <p className="mt-4 text-sm text-[var(--muted)]">در حال خواندن اطلاعات نشست…</p>}
        </section>

        <section className="surface-card p-5">
          <h2 className="font-black">Permissionهای مؤثر</h2>
          <p className="mt-2 text-xs leading-6 text-[var(--muted)]">این لیست از Agency Core خوانده می‌شود و سطح دسترسی واقعی endpointها را نشان می‌دهد.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {permissions.map((permission) => <LtrText key={permission} className="rounded-lg bg-slate-100 px-2.5 py-1.5 text-[11px] text-slate-700">{permission}</LtrText>)}
            {!permissions.length ? <span className="text-sm text-[var(--muted)]">Permissionی بارگذاری نشده است.</span> : null}
          </div>
        </section>
      </div>

      <section className="surface-card mt-5 p-5">
        <h2 className="font-black">Policyهای امنیتی v1</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {[
            ["ثبت‌نام عمومی", "غیرفعال"],
            ["Session", "Opaque + HttpOnly"],
            ["CSRF", "HMAC + Same Origin"],
            ["High/Critical", "Human Approval"],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-[var(--border)] bg-slate-50 p-4">
              <div className="text-xs text-[var(--muted)]">{label}</div>
              <div dir={/[A-Za-z]/.test(value) ? "ltr" : "rtl"} className="mt-2 text-sm font-black">{value}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
