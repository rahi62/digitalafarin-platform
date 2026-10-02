"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main className="railPage provisionPage"><h1>اطلاعات پروژه دریافت نشد</h1><p role="alert">اتصال به پنل مدیریت برقرار نیست. دوباره تلاش کنید.</p><button onClick={reset} className="railPrimaryButton">تلاش دوباره</button></main>;
}
