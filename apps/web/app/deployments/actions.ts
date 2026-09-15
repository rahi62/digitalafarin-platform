"use server";

import { redirect } from "next/navigation";
import { deployService, redeployDeployment, rollbackDeployment } from "@/lib/control-plane";

export async function deployAction(formData: FormData) {
  const serviceId = String(formData.get("service_id") ?? "");
  const commit = String(formData.get("commit") ?? "").trim() || undefined;
  const deployment = await deployService(serviceId, commit);
  redirect(`/deployments/${deployment.id}`);
}

export async function redeployAction(formData: FormData) {
  const deployment = await redeployDeployment(String(formData.get("deployment_id") ?? ""));
  redirect(`/deployments/${deployment.id}`);
}

export async function rollbackAction(formData: FormData) {
  const deployment = await rollbackDeployment(String(formData.get("deployment_id") ?? ""));
  redirect(`/deployments/${deployment.id}`);
}
