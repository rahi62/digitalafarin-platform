"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { db, initializeDatabase } from "@/lib/db";
import { requireAdmin } from "@/lib/session";
import { getSiteConnection } from "@/lib/sites";
import {
  getThemeAutomationStatus,
  updateThemeAutomationPolicy,
  type ThemeAutomationPolicy,
} from "@/lib/theme-automation";

export type ThemeAutomationActionState = { ok?: boolean; error?: string; message?: string };

const HARD_DENY = new Set(["functions.php", "header.php", "footer.php", "index.php"]);
const MAX_FILE_BYTES = 2_097_152;
const MAX_BACKUP_RETENTION = 50;

function normalizeList(value: FormDataEntryValue | null) {
  return String(value ?? "")
    .split(/[\r\n,]+/)
    .map((item) => item.trim().replace(/\\/g, "/"))
    .filter(Boolean);
}

function duplicateEntries(values: string[]) {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const value of values) {
    if (seen.has(value)) duplicates.add(value);
    seen.add(value);
  }
  return [...duplicates];
}

function validRelativeBase(value: string) {
  if (!value || value.startsWith("/") || /^[A-Za-z]:\//.test(value) || value.includes("\0")) return false;
  const parts = value.split("/").filter(Boolean);
  return parts.length > 0 && parts.every((part) => part !== "." && part !== "..");
}

const siteIdSchema = z.string().uuid();

function parsePolicy(formData: FormData): ThemeAutomationPolicy {
  const allowedFiles = normalizeList(formData.get("allowedFiles"));
  const allowedDirectories = normalizeList(formData.get("allowedDirectories")).map((value) => value.replace(/\/+$/, "") + "/");

  const duplicateFiles = duplicateEntries(allowedFiles);
  const duplicateDirectories = duplicateEntries(allowedDirectories);
  if (duplicateFiles.length || duplicateDirectories.length) {
    throw new Error(`مقادیر تکراری مجاز نیستند: ${[...duplicateFiles, ...duplicateDirectories].join("، ")}`);
  }

  for (const file of allowedFiles) {
    if (!validRelativeBase(file) || !file.toLowerCase().endsWith(".php")) {
      throw new Error(`مسیر فایل نامعتبر است: ${file}`);
    }
    if (HARD_DENY.has(file.split("/").pop()!.toLowerCase())) {
      throw new Error(`این فایل به‌صورت سیستمی قابل Write نیست: ${file}`);
    }
  }

  for (const directory of allowedDirectories) {
    if (!validRelativeBase(directory.slice(0, -1))) {
      throw new Error(`مسیر پوشه نامعتبر است: ${directory}`);
    }
  }

  const maxFileBytes = z.coerce.number().int().min(1).max(MAX_FILE_BYTES).parse(formData.get("maxFileBytes"));
  const backupRetentionPerFile = z.coerce.number().int().min(1).max(MAX_BACKUP_RETENTION).parse(formData.get("backupRetentionPerFile"));

  return {
    enabled: formData.get("enabled") === "on",
    fullFileWriteEnabled: formData.get("fullFileWriteEnabled") === "on",
    allowedFiles,
    allowedDirectories,
    maxFileBytes,
    backupRetentionPerFile,
    autoRollbackOnQaFailure: formData.get("autoRollbackOnQaFailure") === "on",
  };
}

export async function updateThemeAutomationAction(
  _state: ThemeAutomationActionState,
  formData: FormData,
): Promise<ThemeAutomationActionState> {
  await requireAdmin();
  try {
    const siteId = siteIdSchema.parse(formData.get("siteId"));
    const policy = parsePolicy(formData);
    const connection = await getSiteConnection(siteId);
    const result = await updateThemeAutomationPolicy(connection, policy);

    await initializeDatabase();
    await db.query(
      "INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'theme.policy_updated',$2)",
      [
        siteId,
        JSON.stringify({
          enabled: result.policy.enabled,
          fullFileWriteEnabled: result.policy.fullFileWriteEnabled,
          allowedFileCount: result.policy.allowedFiles.length,
          allowedDirectoryCount: result.policy.allowedDirectories.length,
          maxFileBytes: result.policy.maxFileBytes,
          backupRetentionPerFile: result.policy.backupRetentionPerFile,
          autoRollbackOnQaFailure: result.policy.autoRollbackOnQaFailure,
        }),
      ],
    );

    revalidatePath(`/sites/${siteId}/theme-automation`);
    revalidatePath("/sites");
    revalidatePath("/audit");
    return { ok: true, message: "Theme Automation با موفقیت ذخیره شد." };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "ذخیره Theme Automation ناموفق بود." };
  }
}

export async function testThemeAutomationAction(
  _state: ThemeAutomationActionState,
  formData: FormData,
): Promise<ThemeAutomationActionState> {
  await requireAdmin();
  try {
    const siteId = siteIdSchema.parse(formData.get("siteId"));
    const connection = await getSiteConnection(siteId);
    const status = await getThemeAutomationStatus(connection);

    await initializeDatabase();
    await db.query(
      "INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'theme.capability_checked',$2)",
      [siteId, JSON.stringify({
        theme: status.theme.stylesheet,
        version: status.theme.version,
        phpLint: status.capabilities.phpLint,
        atomicRename: status.capabilities.atomicRename,
        backup: status.capabilities.backup,
        httpQa: status.capabilities.httpQa,
        zipFallbackRecommended: status.zipFallbackRecommended,
      })],
    );
    revalidatePath(`/sites/${siteId}/theme-automation`);
    revalidatePath("/audit");
    return {
      ok: true,
      message: status.zipFallbackRecommended
        ? "اتصال برقرار است، اما یکی از Safety Gateها ناقص است و ZIP fallback توصیه می‌شود."
        : "اتصال و Safety Gateهای Theme Automation آماده‌اند.",
    };
  } catch (error) {
    return { error: error instanceof Error ? error.message : "بررسی Theme Automation ناموفق بود." };
  }
}
