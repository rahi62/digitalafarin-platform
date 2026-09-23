"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createProject } from "@/lib/control-plane";

export async function createProjectAction(formData: FormData) {
  const name = String(formData.get("name") ?? "").trim();
  const slug = String(formData.get("slug") ?? "").trim();
  const project = await createProject(name, slug);
  revalidatePath("/projects");
  redirect(`/projects/${encodeURIComponent(project.id)}`);
}
