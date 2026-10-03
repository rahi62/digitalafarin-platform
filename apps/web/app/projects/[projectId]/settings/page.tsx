import Link from "next/link";
import { ProjectSettingsForm } from "@/components/SettingsForms";
import { getProject } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function ProjectSettingsPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const project = await getProject(projectId);

  return (
    <main className="railPage">
      <header className="railProjectHeader">
        <div className="railBreadcrumb">
          <Link href="/projects">Projects</Link><span>/</span>
          <Link href={`/projects/${project.id}`}>{project.name}</Link><span>/</span>
          <strong>Settings</strong>
        </div>
        <div className="railProjectTitleRow">
          <div>
            <p className="railEyebrow">PROJECT SETTINGS</p>
            <h1>{project.name}</h1>
            <p>ویرایش metadata پروژه و عملیات حذف محافظت‌شده</p>
          </div>
          <Link className="railSecondaryButton" href={`/projects/${project.id}`}>Back to project</Link>
        </div>
      </header>
      <ProjectSettingsForm project={project} />
    </main>
  );
}
