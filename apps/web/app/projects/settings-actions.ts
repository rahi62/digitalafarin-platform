"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import {
  ControlPlaneError,
  deleteProject,
  getProject,
  removeProjectService,
  updateProject,
  updateProjectService,
} from "@/lib/control-plane";

export type SettingsActionState = { error?: string; success?: string };

function messageFor(error: unknown) {
  if (error instanceof ControlPlaneError) return error.message;
  return error instanceof Error ? error.message : "Unexpected settings error.";
}

function parseObject(value: FormDataEntryValue | null, label: string) {
  let parsed: unknown;
  try {
    parsed = JSON.parse(String(value ?? "{}"));
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

export async function updateProjectSettingsAction(
  _state: SettingsActionState,
  formData: FormData,
): Promise<SettingsActionState> {
  const projectId = String(formData.get("project_id") ?? "");
  try {
    await updateProject(projectId, {
      name: String(formData.get("name") ?? "").trim(),
      slug: String(formData.get("slug") ?? "").trim(),
    });
    revalidatePath("/projects");
    revalidatePath(`/projects/${projectId}`);
    revalidatePath(`/projects/${projectId}/settings`);
    return { success: "Project settings updated." };
  } catch (error) {
    return { error: messageFor(error) };
  }
}

export async function deleteProjectAction(
  _state: SettingsActionState,
  formData: FormData,
): Promise<SettingsActionState> {
  const projectId = String(formData.get("project_id") ?? "");
  try {
    const project = await getProject(projectId);
    if (String(formData.get("confirmation") ?? "") !== project.slug) {
      return { error: "Type the project slug exactly to confirm deletion." };
    }
    await deleteProject(projectId);
  } catch (error) {
    return { error: messageFor(error) };
  }
  revalidatePath("/projects");
  redirect("/projects");
}

export async function updateServiceSettingsAction(
  _state: SettingsActionState,
  formData: FormData,
): Promise<SettingsActionState> {
  const projectId = String(formData.get("project_id") ?? "");
  const serviceId = String(formData.get("service_id") ?? "");
  try {
    await updateProjectService(serviceId, {
      repository: String(formData.get("repository") ?? "").trim(),
      branch: String(formData.get("branch") ?? "").trim(),
      rootDirectory: String(formData.get("root_directory") ?? ".").trim(),
      runtime: String(formData.get("runtime") ?? "") as "node-nextjs" | "python-django",
      servicePort: Number(formData.get("service_port")),
      installConfiguration: parseObject(formData.get("install_configuration"), "Install configuration"),
      buildConfiguration: parseObject(formData.get("build_configuration"), "Build configuration"),
      autoDeploy: formData.get("auto_deploy") === "on",
    });
    revalidatePath(`/projects/${projectId}`);
    revalidatePath(`/projects/${projectId}/services/${serviceId}`);
    revalidatePath(`/services/${serviceId}`);
    return { success: "Service settings updated." };
  } catch (error) {
    return { error: messageFor(error) };
  }
}

export async function removeServiceAction(
  _state: SettingsActionState,
  formData: FormData,
): Promise<SettingsActionState> {
  const projectId = String(formData.get("project_id") ?? "");
  const serviceId = String(formData.get("service_id") ?? "");
  try {
    const project = await getProject(projectId);
    const service = (project.services ?? []).find((item) => item.id === serviceId);
    if (!service) return { error: "Service does not belong to this project." };
    if (String(formData.get("confirmation") ?? "") !== service.unit_name) {
      return { error: "Type the systemd unit name exactly to confirm removal." };
    }
    await removeProjectService(serviceId);
  } catch (error) {
    return { error: messageFor(error) };
  }
  revalidatePath(`/projects/${projectId}`);
  redirect(`/projects/${projectId}`);
}
