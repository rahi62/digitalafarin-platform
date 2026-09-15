"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createServiceLogsOperation, createServiceOperation } from "@/lib/control-plane";
import type { ServiceAction } from "@/lib/operations";

export async function queueServiceOperation(formData: FormData) {
  const serverId = String(formData.get("server_id") ?? "");
  const unitName = String(formData.get("unit_name") ?? "");
  const action = String(formData.get("action") ?? "") as ServiceAction | "logs";
  const operation = action === "logs"
    ? await createServiceLogsOperation(serverId, unitName)
    : await createServiceOperation(serverId, action, unitName, crypto.randomUUID());
  revalidatePath("/operations");
  redirect(`/operations/${operation.id}`);
}
