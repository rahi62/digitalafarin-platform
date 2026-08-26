"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { db, initializeDatabase } from "@/lib/db";
import { disconnectGsc, listGscProperties, testGscConnection } from "@/lib/gsc";
import { requireAdmin } from "@/lib/session";

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
