"use client";

import { useActionState } from "react";
import { createPageDraftAction, updatePageAction } from "@/app/pages/actions";

type PageValues = {
  pageId?: number;
  status?: string;
  title?: string;
  content?: string;
  slug?: string;
  parent?: number;
  menuOrder?: number;
  template?: string;
};

export function PageForm({ siteId, values = {} }: { siteId: string; values?: PageValues }) {
  const editing = Boolean(values.pageId);
  const live = values.status === "publish";
  const [state, action, pending] = useActionState(editing ? updatePageAction : createPageDraftAction, {});
  return <form action={action} className="editor-form">
    <input type="hidden" name="siteId" value={siteId}/>
    {values.pageId && <input type="hidden" name="pageId" value={values.pageId}/>}    
    <div className="editor-main">
      <label>عنوان برگه<input name="title" defaultValue={values.title ?? ""} placeholder="عنوان برگه..." required /></label>
      <label>محتوا <span className="field-hint">HTML قابل استفاده است</span><textarea name="content" defaultValue={values.content ?? ""} rows={24} required /></label>
    </div>
    <aside className="editor-side">
      <div className="editor-card"><h3>تنظیمات برگه</h3>
        <label>اسلاگ<input name="slug" dir="ltr" defaultValue={values.slug ?? ""} placeholder="example-page" pattern="[a-z0-9-]*" /></label>
        <label>Parent ID<input name="parent" inputMode="numeric" dir="ltr" defaultValue={values.parent ?? 0} /></label>
        <label>Menu order<input name="menuOrder" inputMode="numeric" dir="ltr" defaultValue={values.menuOrder ?? 0} /></label>
        <label>Template<input name="template" dir="ltr" defaultValue={values.template ?? ""} placeholder="template-name.php" /></label>
      </div>
      <div className={`editor-card safety-card ${live ? "live-card" : ""}`}><strong>{live ? "ویرایش زنده برگه" : "Workflow کنترل‌شده"}</strong><p>{live ? "ذخیره تغییرات بلافاصله روی برگه منتشرشده اعمال می‌شود." : editing ? "این برگه Draft است و انتشار با عملیات جدا انجام می‌شود." : "برگه جدید ابتدا Draft ساخته می‌شود تا محتوا و SEO قبل از انتشار تکمیل شوند."}</p></div>
      {state.error && <p className="error notice">{state.error}</p>}{state.message && <p className="success notice">{state.message}</p>}
      <button className="primary wide" disabled={pending}>{pending ? "در حال ذخیره…" : !editing ? "ایجاد پیش‌نویس برگه" : live ? "ذخیره روی سایت زنده" : "ذخیره پیش‌نویس"}</button>
    </aside>
  </form>;
}
