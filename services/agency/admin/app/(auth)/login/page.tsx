"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { AgencyApiError, login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      router.replace("/dashboard");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof AgencyApiError ? cause.message : "ورود انجام نشد. دوباره تلاش کنید.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center p-4">
      <section className="surface-card w-full max-w-md overflow-hidden">
        <div className="border-b border-[var(--border)] bg-[var(--primary)] px-6 py-6 text-white">
          <div className="mb-4 grid size-11 place-items-center rounded-2xl bg-white/10 text-sm font-black">DA</div>
          <h1 className="text-xl font-black">ورود به Agency Control Center</h1>
          <p className="mt-2 text-sm leading-6 text-white/70">مدیریت پروژه‌ها، وظایف، دپارتمان‌ها و عملیات حساس دیجیتال‌آفرین.</p>
        </div>

        <form onSubmit={submit} className="grid gap-4 p-6">
          <label className="grid gap-2 text-sm font-semibold text-slate-700">
            ایمیل
            <input
              dir="ltr"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              className="rounded-xl border border-[var(--border)] bg-white px-3 py-3 text-start font-normal outline-none transition focus:border-slate-500"
              placeholder="admin@digitalafarin.ir"
            />
          </label>

          <label className="grid gap-2 text-sm font-semibold text-slate-700">
            رمز عبور
            <input
              dir="ltr"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              className="rounded-xl border border-[var(--border)] bg-white px-3 py-3 text-start font-normal outline-none transition focus:border-slate-500"
            />
          </label>

          {error ? <div className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

          <button
            type="submit"
            disabled={busy}
            className="mt-1 rounded-xl bg-[var(--primary)] px-4 py-3 text-sm font-bold text-white transition hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "در حال ورود…" : "ورود امن"}
          </button>

          <p className="text-center text-xs leading-5 text-[var(--muted)]">ثبت‌نام عمومی غیرفعال است. دسترسی‌ها توسط مدیر سیستم تعریف می‌شوند.</p>
        </form>
      </section>
    </main>
  );
}
