import type { Operation } from '@/lib/control-plane';

const steps = [
  ['preparing', 'آماده‌سازی'],
  ['cloning', 'دریافت کد'],
  ['building', 'نصب و ساخت'],
  ['releasing', 'آماده‌سازی نسخه'],
  ['activating', 'راه‌اندازی سرویس'],
  ['health_check', 'بررسی سلامت'],
  ['verifying', 'تأیید نهایی'],
] as const;

export function DeploymentProgress({ operation }: { operation: Operation }) {
  const stage = operation.progress?.stage ?? 'preparing';
  const rolledBack = operation.result?.final_state === 'rolled_back';
  const current = stage === 'rolling_back' ? steps.findIndex(([key]) => key === 'health_check') : steps.findIndex(([key]) => key === stage);
  const complete = operation.state === 'succeeded' && !rolledBack;
  const failed = operation.state === 'failed' || rolledBack;

  return <section className="deploymentProgress" aria-label="مراحل استقرار" aria-live="polite">
    <div className="deploymentProgressHeader">
      <strong>{complete ? 'استقرار موفق' : rolledBack ? 'استقرار ناموفق؛ نسخهٔ قبلی بازیابی شد' : failed ? 'استقرار ناموفق' : 'استقرار در حال انجام'}</strong>
      <span>{operation.progress?.reported_at ? `آخرین گزارش: ${new Date(operation.progress.reported_at).toLocaleTimeString('fa-IR')}` : 'در انتظار گزارش Agent'}</span>
    </div>
    <ol className="deploymentProgressSteps">
      {steps.map(([key, label], index) => {
        const state = complete || index < current ? 'done' : index === current ? failed ? 'failed' : 'active' : 'pending';
        return <li key={key} className={`deploymentStep deploymentStep-${state}`}>
          <span className="deploymentStepMarker" aria-hidden="true">{state === 'done' ? '✓' : index + 1}</span>
          <span>{label}</span>
          {state === 'active' && <small>در حال انجام</small>}
          {state === 'failed' && <small>ناموفق</small>}
        </li>;
      })}
    </ol>
    {failed && <div className="deploymentFailure" role="alert">
      <strong>{operation.error_code || String(operation.result?.failure_code || 'خطای استقرار')}</strong>
      {Boolean(operation.error_message || operation.result?.failure_message) && <p dir="auto">{String(operation.error_message || operation.result?.failure_message)}</p>}
    </div>}
  </section>;
}
