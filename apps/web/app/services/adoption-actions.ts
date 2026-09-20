"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { adoptService, configureServiceDeployment } from "@/lib/control-plane";

export async function adoptExistingServiceAction(formData: FormData) {
  const projectId = String(formData.get("project_id") ?? "");
  const serverId = String(formData.get("server_id") ?? "");
  const unitName = String(formData.get("unit_name") ?? "");
  const name = String(formData.get("name") ?? "").trim();
  const service = await adoptService(projectId, serverId, unitName, name);
  revalidatePath(`/projects/${projectId}`);
  redirect(`/services/${service.id}`);
}

export async function configureDeploymentAction(formData: FormData) {
  const serviceId = String(formData.get("service_id") ?? "");
  const runtime = String(formData.get("runtime") ?? "") as "node-nextjs" | "python-django";
  const servicePort = Number(formData.get("service_port"));
  const installConfiguration = JSON.parse(
    String(formData.get("install_configuration") ?? "{}"),
  ) as Record<string, unknown>;
  const buildConfiguration = JSON.parse(
    String(formData.get("build_configuration") ?? "{}"),
  ) as Record<string, unknown>;
  await configureServiceDeployment(serviceId, {
    repository: String(formData.get("repository") ?? "").trim(),
    branch: String(formData.get("branch") ?? "").trim(),
    rootDirectory: String(formData.get("root_directory") ?? ".").trim(),
    runtime,
    servicePort,
    installConfiguration,
    buildConfiguration,
  });
  revalidatePath(`/services/${serviceId}`);
  redirect(`/services/${serviceId}`);
}
