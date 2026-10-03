import { redirect } from "next/navigation";
import { registerGitHubInstallation } from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function GitHubCallbackPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const rawInstallation = Array.isArray(params.installation_id) ? params.installation_id[0] : params.installation_id;
  const state = Array.isArray(params.state) ? params.state[0] : params.state;
  const installationId = Number(rawInstallation);
  if (!Number.isSafeInteger(installationId) || installationId <= 0 || !state) {
    return <main className="railPage"><h1>GitHub connection failed</h1><p>Invalid installation callback.</p></main>;
  }
  try {
    await registerGitHubInstallation(installationId, state);
  } catch (error) {
    return <main className="railPage"><h1>GitHub connection failed</h1><p>{error instanceof Error ? error.message : "Unable to verify GitHub installation."}</p></main>;
  }
  redirect("/settings?github=connected");
}
