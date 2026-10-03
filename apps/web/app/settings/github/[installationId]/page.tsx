import Link from "next/link";
import { listGitHubRepositories } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function GitHubRepositoriesPage({
  params,
}: {
  params: Promise<{ installationId: string }>;
}) {
  const { installationId } = await params;
  const id = Number(installationId);
  const repositories = await listGitHubRepositories(id);
  return (
    <main className="railPage">
      <header className="railProjectHeader">
        <div><p className="railEyebrow">SETTINGS / GITHUB</p><h1>Authorized repositories</h1><p>Repositoryهایی که GitHub App اجازه دسترسی به آن‌ها را دارد.</p></div>
        <Link className="railSecondaryButton" href="/settings">Back to Settings</Link>
      </header>
      <section className="railServiceSection">
        <div className="railDeploymentList">
          {repositories.map((repository) => (
            <div className="railDeploymentRow" key={repository.id}>
              <div><strong>{repository.full_name}</strong><small>{repository.private ? "Private" : "Public"} · default: {repository.default_branch}</small></div>
              <span className="railFormSuccess">Authorized</span>
            </div>
          ))}
          {repositories.length === 0 && <div className="railEmpty railEmptyCompact"><h3>No repositories authorized</h3><p>GitHub App installation را ویرایش و repository دسترسی‌پذیر اضافه کنید.</p></div>}
        </div>
      </section>
    </main>
  );
}
