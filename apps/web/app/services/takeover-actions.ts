"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import {
  activateTakeover,
  cancelTakeover,
  prepareServiceTakeover,
} from "@/lib/control-plane";

export async function prepareTakeoverAction(formData: FormData) {
  const serviceId = String(formData.get("service_id") ?? "");
  const commit = String(formData.get("commit") ?? "").trim();
  await prepareServiceTakeover(serviceId, commit);
  revalidatePath(`/services/${serviceId}`);
  redirect(`/services/${serviceId}`);
}

export async function activateTakeoverAction(formData: FormData) {
  const serviceId = String(formData.get("service_id") ?? "");
  const takeoverId = String(formData.get("takeover_id") ?? "");
  await activateTakeover(takeoverId);
  revalidatePath(`/services/${serviceId}`);
  redirect(`/services/${serviceId}`);
}

export async function cancelTakeoverAction(formData: FormData) {
  const serviceId = String(formData.get("service_id") ?? "");
  const takeoverId = String(formData.get("takeover_id") ?? "");
  await cancelTakeover(takeoverId);
  revalidatePath(`/services/${serviceId}`);
  redirect(`/services/${serviceId}`);
}
