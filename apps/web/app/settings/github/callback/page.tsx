import { redirect } from "next/navigation";
import {
  registerGitHubInstallation,
  verifyGitHubInstallation,
} from "@/lib/control-plane";

export const dynamic = "force-dynamic";

export default async function GitHubCallbackPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const rawInstallation = Array.isArray(params.installation_id)
    ? params.installation_id[0]
    : params.installation_id;
  const state = Array.isArray(params.state) ? params.state[0] : params.state;
  const setupAction = Array.isArray(params.setup_action)
    ? params.setup_action[0]
    : params.setup_action;
  const installationId = Number(rawInstallation);

  if (!Number.isSafeInteger(installationId) || installationId <= 0) {
    return (
      <main className="railPage">
        <h1>GitHub connection failed</h1>
        <p>Invalid installation callback.</p>
      </main>
    );
  }

  let failure = "";
  if (!state && setupAction !== "install" && setupAction !== "update") {
    failure = "Missing installation verification context.";
  } else {
    try {
      if (state) {
        await registerGitHubInstallation(installationId, state);
      } else {
        await verifyGitHubInstallation(installationId);
      }
    } catch (error) {
      failure = error instanceof Error
        ? error.message
        : "Unable to verify GitHub installation.";
    }
  }

  if (failure) {
    return (
      <main className="railPage">
        <h1>GitHub connection failed</h1>
        <p>{failure}</p>
      </main>
    );
  }

  redirect("/settings?github=connected");
}
