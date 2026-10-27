"use client";

import { useActionState } from "react";
import { loginAction } from "../actions";

export default function LoginPage() {
  const [state, action, pending] = useActionState(loginAction, {});
  return <main className="login-shell"><section className="login-card">
    <div className="brand-mark">DA</div><p className="eyebrow">DIGITALAFARIN</p>
    <h1>ورود به WP Agent</h1><p className="muted">مرکز مدیریت امن سایت‌های وردپرسی</p>
    <form action={action} className="form-stack"><label>رمز عبور مدیر<input name="password" type="password" required autoFocus /></label>
      {state.error && <p className="error">{state.error}</p>}<button disabled={pending}>{pending ? "در حال بررسی…" : "ورود امن"}</button></form>
  </section></main>;
}
