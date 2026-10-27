"use client";

import { useActionState } from "react";
import {
  testThemeAutomationAction,
  updateThemeAutomationAction,
} from "@/app/sites/[siteId]/theme-automation/actions";
import type { ThemeAutomationPolicy } from "@/lib/theme-automation";

type Props = {
  siteId: string;
  policy: ThemeAutomationPolicy;
  hardDeniedFiles: string[];
  maxFileBytes: number;
  maxBackupRetentionPerFile: number;
};

export function ThemeAutomationForm({
  siteId,
  policy,
  hardDeniedFiles,
  maxFileBytes,
  maxBackupRetentionPerFile,
}: Props) {
  const [saveState, saveAction, saving] = useActionState(updateThemeAutomationAction, {});
  const [testState, testAction, testing] = useActionState(testThemeAutomationAction, {});

  return <div className="theme-automation-form-wrap">
    <form action={saveAction} className="form-stack">
      <input type="hidden" name="siteId" value={siteId} />

      <div className="form-grid">
        <label className="checkbox-field">
          <span>Theme Automation</span>
          <input name="enabled" type="checkbox" defaultChecked={policy.enabled} />
          <small>Discovery و Read فقط وقتی این policy فعال باشد.</small>
        </label>
        <label className="checkbox-field">
          <span>Full-file template write</span>
          <input name="fullFileWriteEnabled" type="checkbox" defaultChecked={policy.fullFileWriteEnabled} />
          <small>Write همچنان به allowlist، hash، lint، backup و QA وابسته است.</small>
        </label>
      </div>

      <label>فایل‌های مجاز
        <textarea
          name="allowedFiles"
          rows={7}
          defaultValue={policy.allowedFiles.join("\n")}
          placeholder={"templates/pillar-property-loan.php\ntemplates/pillar-car-loan.php"}
        />
        <small>هر خط یک مسیر نسبی PHP داخل قالب فعال.</small>
      </label>

      <label>پوشه‌های مجاز
        <textarea
          name="allowedDirectories"
          rows={5}
          defaultValue={policy.allowedDirectories.join("\n")}
          placeholder={"templates/pillars/\ntemplate-parts/pillars/"}
        />
        <small>Agent فقط فایل‌های PHP داخل این مسیرهای نسبی را می‌تواند مدیریت کند.</small>
      </label>

      <div className="form-grid">
        <label>حداکثر اندازه فایل (byte)
          <input
            name="maxFileBytes"
            type="number"
            min={1}
            max={maxFileBytes}
            defaultValue={policy.maxFileBytes}
            required
          />
        </label>
        <label>تعداد Backup برای هر فایل
          <input
            name="backupRetentionPerFile"
            type="number"
            min={1}
            max={maxBackupRetentionPerFile}
            defaultValue={policy.backupRetentionPerFile}
            required
          />
        </label>
      </div>

      <label className="checkbox-field">
        <span>Rollback خودکار بعد از QA ناموفق</span>
        <input name="autoRollbackOnQaFailure" type="checkbox" defaultChecked={policy.autoRollbackOnQaFailure} />
      </label>

      <div className="security-note">
        <strong>Hard deny</strong>
        <p>{hardDeniedFiles.join(" · ")}</p>
        <small>این فایل‌ها حتی با Administrator و حتی اگر وارد allowlist شوند، مستقیم Write نمی‌شوند.</small>
      </div>

      {saveState.error && <p className="error">{saveState.error}</p>}
      {saveState.message && <p className="success">{saveState.message}</p>}
      <button disabled={saving}>{saving ? "در حال ذخیره…" : "ذخیره Theme Automation"}</button>
    </form>

    <form action={testAction} className="theme-test-form">
      <input type="hidden" name="siteId" value={siteId} />
      {testState.error && <p className="error">{testState.error}</p>}
      {testState.message && <p className="success">{testState.message}</p>}
      <button className="secondary" disabled={testing}>{testing ? "در حال بررسی…" : "تست Safety Gateها"}</button>
    </form>
  </div>;
}
