"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { createBootstrapOperation, createProject } from "@/lib/control-plane";

export async function queueBootstrap(formData: FormData) {
  const serverId = String(formData.get("server_id") ?? "").trim();
  const idempotencyKey = String(formData.get("idempotency_key") ?? "").trim();
  if (!serverId) throw new Error("server_id is required");
  await createBootstrapOperation(serverId, idempotencyKey);
  revalidatePath("/migration");
}

export async function createMigrationProject(formData: FormData) {
  const name = String(formData.get("name") ?? "");
  const slug = String(formData.get("slug") ?? "");
  const project = await createProject(name, slug);
  revalidatePath("/migration");
  redirect(`/migration?project=${encodeURIComponent(project.id)}`);
}
