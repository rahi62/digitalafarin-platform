"use client";

import { useActionState } from "react";
import { saveGscOAuthConfigAction } from "@/app/settings/actions";

export function GscOAuthConfigForm({
  clientId,
  hasClientSecret,
  callbackUrl,
}: {
  clientId: string;
  hasClientSecret: boolean;
  callbackUrl: string;
}) {
  const [state, action, pending] = useActionState(saveGscOAuthConfigAction, {});
  return <form action={action} className="form-stack oauth-config-form">
    <label>Google Client ID
      <input name="clientId" dir="ltr" defaultValue={clientId} placeholder="xxxxxxxx.apps.googleusercontent.com" required />
    </label>
    <label>Google Client Secret <span className="field-hint">{hasClientSecret ? "برای حفظ مقدار فعلی خالی بگذارید" : "برای اولین تنظیم الزامی است"}</span>
      <input name="clientSecret" dir="ltr" type="password" autoComplete="new-password" placeholder={hasClientSecret ? "••••••••••••••••" : "GOCSPX-..."} />
    </label>
    <label>Authorized redirect URI <span className="field-hint">این مقدار را عیناً در Google Cloud ثبت کنید</span>
      <input dir="ltr" value={callbackUrl} readOnly className="readonly-input" />
    </label>
    {state.error && <p className="error notice">{state.error}</p>}
    {state.message && <p className="success notice">{state.message}</p>}
    <button className="primary" type="submit" disabled={pending}>{pending ? "در حال ذخیره…" : hasClientSecret ? "ذخیره تنظیمات OAuth" : "ثبت Google OAuth App"}</button>
  </form>;
}
