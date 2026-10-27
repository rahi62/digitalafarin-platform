"use server";

import { randomUUID, timingSafeEqual } from "node:crypto";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import { dashboardConfig, passwordDigest } from "@/lib/config";
import { decryptSecret, encryptSecret } from "@/lib/crypto";
import { db, initializeDatabase } from "@/lib/db";
import { clearSession, createSession, requireAdmin } from "@/lib/session";
import { checkWordPressConnection } from "@/lib/wordpress";

export type ActionState = { ok?: boolean; error?: string; message?: string };

const siteSchema = z.object({
  name: z.string().trim().min(2).max(160),
  baseUrl: z.string().trim().url().refine((value) => value.startsWith("https://"), "HTTPS الزامی است"),
  username: z.string().trim().min(1).max(160),
  appPassword: z.string().trim().min(10).max(200),
});

export async function loginAction(_state: ActionState, formData: FormData): Promise<ActionState> {
  const supplied = passwordDigest(String(formData.get("password") ?? ""));
  const expected = dashboardConfig.adminPasswordHash;
  const a = Buffer.from(supplied);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return { error: "رمز عبور صحیح نیست." };
  await createSession();
  redirect("/");
}

export async function logoutAction() {
  await clearSession();
  redirect("/login");
}

export async function addSiteAction(_state: ActionState, formData: FormData): Promise<ActionState> {
  await requireAdmin();
  const parsed = siteSchema.safeParse({
    name: formData.get("name"), baseUrl: formData.get("baseUrl"),
    username: formData.get("username"), appPassword: formData.get("appPassword"),
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "اطلاعات فرم معتبر نیست." };
  const input = { ...parsed.data, baseUrl: parsed.data.baseUrl.replace(/\/$/, "") };
  try {
    const user = await checkWordPressConnection(input);
    await initializeDatabase();
    const id = randomUUID();
    await db.query(
      `INSERT INTO wordpress_sites (id,name,base_url,username,encrypted_app_password,last_check_status,last_check_message,last_checked_at)
       VALUES ($1,$2,$3,$4,$5,'ok',$6,NOW())`,
      [id, input.name, input.baseUrl, input.username, encryptSecret(input.appPassword.replace(/\s+/g, "")), `Connected as ${user.name ?? input.username}`],
    );
    await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'site.created',$2)", [id, JSON.stringify({ baseUrl: input.baseUrl, username: input.username })]);
    revalidatePath("/"); revalidatePath("/sites"); revalidatePath("/content");
    return { ok: true, message: "سایت با موفقیت اضافه و اتصال آن تأیید شد." };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "افزودن سایت ناموفق بود." };
  }
}

export async function toggleSiteAction(formData: FormData) {
  await requireAdmin();
  await initializeDatabase();
  const id = z.string().uuid().parse(formData.get("id"));
  await db.query("UPDATE wordpress_sites SET enabled=NOT enabled,updated_at=NOW() WHERE id=$1", [id]);
  await db.query("INSERT INTO audit_logs (site_id,action) VALUES ($1,'site.toggled')", [id]);
  revalidatePath("/"); revalidatePath("/sites"); revalidatePath("/content");
}

export async function checkSiteAction(formData: FormData) {
  await requireAdmin();
  await initializeDatabase();
  const id = z.string().uuid().parse(formData.get("id"));
  const result = await db.query<{ base_url: string; username: string; encrypted_app_password: string }>(
    "SELECT base_url,username,encrypted_app_password FROM wordpress_sites WHERE id=$1 LIMIT 1", [id],
  );
  const site = result.rows[0];
  if (!site) return;
  try {
    const user = await checkWordPressConnection({ baseUrl: site.base_url, username: site.username, appPassword: decryptSecret(site.encrypted_app_password) });
    await db.query("UPDATE wordpress_sites SET last_check_status='ok',last_check_message=$2,last_checked_at=NOW(),updated_at=NOW() WHERE id=$1", [id, `Connected as ${user.name ?? site.username}`]);
    await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'site.health_checked',$2)", [id, JSON.stringify({ status: "ok", roles: user.roles })]);
  } catch (error) {
    const message = error instanceof Error ? error.message.slice(0, 500) : "Connection failed";
    await db.query("UPDATE wordpress_sites SET last_check_status='error',last_check_message=$2,last_checked_at=NOW(),updated_at=NOW() WHERE id=$1", [id, message]);
    await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'site.health_checked',$2)", [id, JSON.stringify({ status: "error", message })]);
  }
  revalidatePath("/"); revalidatePath("/sites");
}
