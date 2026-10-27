import Link from "next/link";

export function ContentTabs({ active, siteId }: { active: "posts" | "pages"; siteId?: string }) {
  const suffix = siteId ? `?siteId=${siteId}` : "";
  return <div className="site-actions" style={{ marginBottom: 14 }}>
    <Link className={`button-link ${active === "posts" ? "primary" : "secondary"}`} href={`/content${suffix}`}>نوشته‌ها</Link>
    <Link className={`button-link ${active === "pages" ? "primary" : "secondary"}`} href={`/pages${suffix}`}>برگه‌ها</Link>
  </div>;
}
