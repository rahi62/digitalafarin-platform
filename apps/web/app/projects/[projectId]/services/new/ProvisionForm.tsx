"use client";

import { useActionState, useState } from 'react';
import Link from 'next/link';
import type { ServerSummary } from '@/lib/control-plane';
import { provisionAction } from './actions';

export function ProvisionForm({ projectId, requestId, servers }: { projectId: string; requestId: string; servers: ServerSummary[] }) {
  const [state, action, pending] = useActionState(provisionAction, { error: '' });
  const [name, setName] = useState('web');
  const ready = servers.filter(server => server.status === 'online' && server.capabilities.includes('service_provision_v1'));
  const preferred = ready.find(server => server.is_default) ?? ready[0];
  return <div className="provisionLayout" dir="rtl">
    <form action={action} className="provisionForm" aria-busy={pending}>
      <input type="hidden" name="project_id" value={projectId} />
      <input type="hidden" name="request_id" value={requestId} />
      <fieldset disabled={pending}>
        <legend><span className="provisionNumber">۱</span> مخزن و برنامه</legend>
        <p className="provisionHint">مخزن عمومی برنامهٔ Next.js خود را متصل کنید.</p>
        <label htmlFor="repository">آدرس مخزن Git <span>الزامی</span></label>
        <input id="repository" name="repository" type="url" required dir="ltr" placeholder="https://github.com/your-team/your-app" autoComplete="off" />
        <small>GitHub، GitLab و Bitbucket · مخزن باید package-lock.json داشته باشد.</small>
        <div className="provisionFields">
          <div><label htmlFor="service-name">نام سرویس</label><input id="service-name" name="name" required pattern="[a-z0-9][a-z0-9_-]{0,79}" maxLength={80} value={name} onChange={event => setName(event.target.value)} dir="ltr" /></div>
          <div><label htmlFor="branch">Branch</label><input id="branch" name="branch" defaultValue="main" required dir="ltr" /></div>
        </div>
        <label htmlFor="root-directory">پوشهٔ برنامه در مخزن</label>
        <input id="root-directory" name="root_directory" defaultValue="." required dir="ltr" />
        <small>برای monorepo مانند apps/web؛ برای ریشهٔ مخزن یک نقطه.</small>
      </fieldset>
      <fieldset disabled={pending}>
        <legend><span className="provisionNumber">۲</span> محل اجرا</legend>
        <label htmlFor="server">سرور مقصد</label>
        <select id="server" name="server_id" required defaultValue={preferred?.id ?? ''}>
          <option value="" disabled>سرور آماده انتخاب کنید</option>
          {servers.map(server => <option key={server.id} value={server.id} disabled={!ready.some(item => item.id === server.id)}>{server.name} · {server.status === 'online' ? (server.capabilities.includes('service_provision_v1') ? 'آماده' : 'نیازمند بروزرسانی') : 'در دسترس نیست'}</option>)}
        </select>
        {ready.length === 0 && <p className="provisionNotice" role="status">سرور آماده‌ای وجود ندارد. <Link href="/servers">وضعیت سرورها را بررسی کنید</Link>.</p>}
        <label htmlFor="runtime">محیط اجرا</label>
        <select id="runtime" name="runtime" defaultValue="node-nextjs" required><option value="node-nextjs">Next.js · Node.js</option></select>
        <div className="provisionFields">
          <div><label htmlFor="port">پورت داخلی</label><input id="port" type="number" name="service_port" min={1024} max={65535} required dir="ltr" placeholder="3000" /></div>
          <div><label htmlFor="health-path">مسیر بررسی سلامت</label><input id="health-path" name="health_path" defaultValue="/" required dir="ltr" /></div>
        </div>
        <small>این مسیر باید بعد از راه‌اندازی پاسخ ۲۰۰ بدهد. پورت برنامه فقط روی localhost باز می‌شود.</small>
      </fieldset>
      <div className="provisionFooter">
        {state.error && <p className="provisionError" role="alert">{state.error}</p>}
        <button className="provisionSubmit" disabled={pending || ready.length === 0} type="submit">{pending ? 'در حال ثبت درخواست…' : 'ساخت و دیپلوی سرویس'}<span aria-hidden="true">←</span></button>
        <p>پیشرفت ساخت و نتیجهٔ بررسی سلامت در صفحهٔ سرویس نمایش داده می‌شود.</p>
      </div>
    </form>
    <aside className="provisionSummary">
      <span className="provisionEyebrow">سرویس جدید</span>
      <div className="provisionPreviewIcon" aria-hidden="true">N</div>
      <h2><bdi>{name || 'سرویس شما'}</bdi></h2>
      <p>Next.js · Node.js</p>
      <dl><div><dt>نصب وابستگی‌ها</dt><dd dir="ltr">npm ci</dd></div><div><dt>ساخت برنامه</dt><dd dir="ltr">npm run build</dd></div><div><dt>انتشار</dt><dd>پس از بررسی سلامت</dd></div></dl>
      <ol className="provisionJourney"><li>دریافت نسخهٔ دقیق از Git</li><li>نصب و ساخت برنامه</li><li>راه‌اندازی سرویس</li><li>بررسی سلامت و ثبت نتیجه</li></ol>
      <p className="provisionSummaryNote">در این مرحله مخزن عمومی Next.js پشتیبانی می‌شود. متغیرها و فضای ذخیره‌سازی به مراحل بعدی توسعه اضافه می‌شوند.</p>
    </aside>
  </div>;
}
