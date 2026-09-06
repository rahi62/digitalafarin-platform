"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  createTelegramChannel,
  setTelegramCredential,
  testTelegramChannel,
  updateTelegramChannel,
} from "@/lib/telegram";
import { normalizeTelegramAlias, validateTelegramAlias } from "@/lib/telegram-utils";

function value(formData: FormData, key: string): string {
  return String(formData.get(key) ?? "").trim();
}

function finish(kind: "notice" | "error", message: string): never {
  redirect(`/bot?${kind}=${encodeURIComponent(message.slice(0, 180))}`);
}

function safeMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "عملیات انجام نشد.";
}

export async function setBotTokenAction(formData: FormData) {
  const token = value(formData, "token");
  const name = value(formData, "name") || "primary";
  if (!token) finish("error", "توکن ربات الزامی است.");
  try {
    await setTelegramCredential({ token, name });
    revalidatePath("/bot");
  } catch (error) {
    finish("error", safeMessage(error));
  }
  finish("notice", "توکن ربات اعتبارسنجی و ذخیره شد.");
}

export async function createChannelAction(formData: FormData) {
  const alias = normalizeTelegramAlias(value(formData, "alias"));
  const name = value(formData, "name");
  const chatId = value(formData, "chat_id");
  const description = value(formData, "description");

  if (!validateTelegramAlias(alias)) finish("error", "Alias فقط می‌تواند شامل حروف انگلیسی، عدد، - و _ باشد.");
  if (!name || !chatId) finish("error", "نام و Chat ID کانال الزامی است.");

  try {
    await createTelegramChannel({ alias, name, chat_id: chatId, description, is_active: true });
    revalidatePath("/bot");
  } catch (error) {
    finish("error", safeMessage(error));
  }
  finish("notice", `کانال ${alias} اضافه شد.`);
}

export async function updateChannelAction(formData: FormData) {
  const id = value(formData, "id");
  const alias = normalizeTelegramAlias(value(formData, "alias"));
  const name = value(formData, "name");
  const chatId = value(formData, "chat_id");
  const description = value(formData, "description");
  const isActive = value(formData, "is_active") === "true";

  if (!id) finish("error", "شناسه کانال نامعتبر است.");
  if (!validateTelegramAlias(alias)) finish("error", "Alias کانال نامعتبر است.");
  if (!name || !chatId) finish("error", "نام و Chat ID کانال الزامی است.");

  try {
    await updateTelegramChannel(id, {
      alias,
      name,
      chat_id: chatId,
      description,
      is_active: isActive,
    });
    revalidatePath("/bot");
  } catch (error) {
    finish("error", safeMessage(error));
  }
  finish("notice", `کانال ${alias} ذخیره شد.`);
}

export async function toggleChannelAction(formData: FormData) {
  const id = value(formData, "id");
  const alias = value(formData, "alias");
  const nextActive = value(formData, "next_active") === "true";
  if (!id) finish("error", "شناسه کانال نامعتبر است.");
  try {
    await updateTelegramChannel(id, { is_active: nextActive });
    revalidatePath("/bot");
  } catch (error) {
    finish("error", safeMessage(error));
  }
  finish("notice", `${alias || "کانال"} ${nextActive ? "فعال" : "غیرفعال"} شد.`);
}

export async function testChannelAction(formData: FormData) {
  const id = value(formData, "id");
  const alias = value(formData, "alias");
  if (!id) finish("error", "شناسه کانال نامعتبر است.");
  try {
    await testTelegramChannel(id);
    revalidatePath("/bot");
  } catch (error) {
    finish("error", safeMessage(error));
  }
  finish("notice", `پیام تست برای ${alias || "کانال"} ارسال شد.`);
}
