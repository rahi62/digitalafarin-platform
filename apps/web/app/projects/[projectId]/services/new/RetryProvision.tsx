"use client";

import { useActionState } from 'react';
import { retryProvisionAction } from './actions';

export function RetryProvision({ projectId, serviceId, requestId }: { projectId: string; serviceId: string; requestId: string }) {
  const [state, action, pending] = useActionState(retryProvisionAction, { error: '' });
  return <form action={action}>
    <input type="hidden" name="project_id" value={projectId} />
    <input type="hidden" name="service_id" value={serviceId} />
    <input type="hidden" name="request_id" value={requestId} />
    {state.error && <p role="alert">{state.error}</p>}
    <button disabled={pending} type="submit">{pending ? 'در حال ثبت…' : 'تلاش دوباره برای راه‌اندازی'}</button>
  </form>;
}
