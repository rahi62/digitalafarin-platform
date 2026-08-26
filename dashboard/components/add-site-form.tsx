"use client";

import { useActionState } from "react";
import { addSiteAction } from "@/app/actions";

export function AddSiteForm() {
  const [state, action, pending] = useActionState(addSiteAction, {});
  return <form action={action} className="form-stack">
    <div className="form-grid"><label>نام سایت<input name="name" placeholder="وام فوری ۲۴" required /></label><label>آدرس سایت<input name="baseUrl" type="url" placeholder="https://example.com" required /></label></div>
    <div className="form-grid"><label>نام کاربری API<input name="username" autoComplete="off" required /></label><label>Application Password<input name="appPassword" type="password" autoComplete="new-password" required /></label></div>
    {state.error && <p className="error">{state.error}</p>}{state.message && <p className="success">{state.message}</p>}
    <button disabled={pending}>{pending ? "در حال تست اتصال…" : "تست اتصال و افزودن سایت"}</button>
  </form>;
}
