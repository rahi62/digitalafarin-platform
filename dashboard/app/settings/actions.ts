"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { db, initializeDatabase } from "@/lib/db";
import { disconnectGsc, listGscProperties, testGscConnection } from "@/lib/gsc";
import { clearGscOAuthCredentials, saveGscOAuthCredentials } from "@/lib/integration-settings";
import { requireAdmin } from "@/lib/session";

export type IntegrationActionState = { error?: string; message?: string };

const oauthAppSchema = z.object({
  clientId: z.string().trim().min(10, "Google Client ID الزامی است.").max(500),
  clientSecret: z.string().trim().max(1000).optional(),
});

export async function saveGscOAuthConfigAction(_state: IntegrationActionState, formData: FormData): Promise<IntegrationActionState> {
  await requireAdmin();
  const parsed = oauthAppSchema.safeParse({
    clientId: formData.get("clientId"),
    clientSecret: String(formData.get("clientSecret") ?? "").trim() || undefined,
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "تنظیمات OAuth معتبر نیست." };

  try {
    const result = await saveGscOAuthCredentials(parsed.data);
    revalidatePath("/settings");
    revalidatePath("/");
    return {
      message: result.credentialsChanged
        ? "تنظیمات Google OAuth ذخیره شد. برای امنیت، اتصال قبلی Search Console ریست شد و باید دوباره Connect شود."
        : "تنظیمات Google OAuth ذخیره شد.",
    };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "ذخیره تنظیمات OAuth ناموفق بود." };
  }
}

export async function clearGscOAuthConfigAction() {
  await requireAdmin();
  await clearGscOAuthCredentials();
  revalidatePath("/settings");
  revalidatePath("/");
}

export async function saveGscPropertyAction(formData: FormData) {
  await requireAdmin();
  const siteId = z.string().uuid().parse(formData.get("siteId"));
  const propertyUrl = String(formData.get("propertyUrl") ?? "").trim();
  await initializeDatabase();

  if (propertyUrl) {
    const properties = await listGscProperties();
    if (!properties.some((property) => property.siteUrl === propertyUrl)) {
      throw new Error("این Property در حساب متصل Search Console در دسترس نیست.");
    }
  }

  await db.query("UPDATE wordpress_sites SET gsc_property_url=$2,updated_at=NOW() WHERE id=$1", [siteId, propertyUrl || null]);
  await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'gsc.property_mapped',$2)", [siteId, JSON.stringify({ propertyUrl: propertyUrl || null })]);
  revalidatePath("/settings");
  revalidatePath("/");
}

export async function testGscAction() {
  await requireAdmin();
  await testGscConnection();
  revalidatePath("/settings");
  revalidatePath("/");
}

export async function disconnectGscAction() {
  await requireAdmin();
  await disconnectGsc();
  revalidatePath("/settings");
  revalidatePath("/");
}
