"use client";

import { useActionState } from "react";
import { createDraftAction, updatePostAction } from "@/app/content/actions";
import type { WordPressCategory } from "@/lib/wordpress";

type DraftValues = {
  postId?: number;
  status?: string;
  title?: string;
  content?: string;
  excerpt?: string;
  slug?: string;
  categoryIds?: number[];
};

export function DraftForm({ siteId, categories, values = {} }: { siteId: string; categories: WordPressCategory[]; values?: DraftValues }) {
  const editing = Boolean(values.postId);
  const live = values.status === "publish";
  const [state, action, pending] = useActionState(editing ? updatePostAction : createDraftAction, {});
  return (
    <form action={action} className="editor-form">
      <input type="hidden" name="siteId" value={siteId} />
      {values.postId && <input type="hidden" name="postId" value={values.postId} />}
      <div className="editor-main">
        <label>عنوان نوشته<input name="title" defaultValue={values.title ?? ""} placeholder="عنوان مقاله یا صفحه..." required /></label>
        <label>محتوا <span className="field-hint">HTML قابل استفاده است</span><textarea name="content" defaultValue={values.content ?? ""} rows={22} required /></label>
        <label>خلاصه<textarea name="excerpt" defaultValue={values.excerpt ?? ""} rows={5} placeholder="خلاصه اختیاری نوشته" /></label>
      </div>
      <aside className="editor-side">
        <div className="editor-card"><h3>تنظیمات نوشته</h3><label>اسلاگ<input name="slug" dir="ltr" defaultValue={values.slug ?? ""} placeholder="example-post-slug" pattern="[a-z0-9-]*" /></label></div>
        <div className="editor-card"><h3>دسته‌بندی‌ها</h3><div className="category-list">{categories.length === 0 ? <p className="muted">دسته‌بندی‌ای پیدا نشد.</p> : categories.map((category) => <label className="check-row" key={category.id}><input type="checkbox" name="categoryIds" value={category.id} defaultChecked={values.categoryIds?.includes(category.id)} /><span>{category.name}</span><small>{category.count}</small></label>)}</div></div>
        <div className={`editor-card safety-card ${live ? "live-card" : ""}`}><strong>{live ? "ویرایش زنده" : "Workflow کنترل‌شده"}</strong><p>{live ? "این نوشته منتشرشده است؛ ذخیره تغییرات بلافاصله روی سایت زنده اعمال می‌شود. حذف محتوا از این پنل پشتیبانی نمی‌شود." : editing ? "این نوشته هنوز Draft است. ابتدا تغییرات را ذخیره کنید و سپس در صورت نیاز از عملیات جداگانه انتشار استفاده کنید." : "نوشته جدید ابتدا به صورت Draft ساخته می‌شود تا محتوا، تصاویر و SEO قبل از انتشار کامل شوند."}</p></div>
        {state.error && <p className="error notice">{state.error}</p>}{state.message && <p className="success notice">{state.message}</p>}
        <button className="primary wide" disabled={pending}>{pending ? "در حال ذخیره…" : !editing ? "ایجاد پیش‌نویس" : live ? "ذخیره روی سایت زنده" : "ذخیره پیش‌نویس"}</button>
      </aside>
    </form>
  );
}
