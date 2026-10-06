import { DeploymentLiveRefresh } from "@/components/DeploymentLiveRefresh";
import { getDeployment } from "@/lib/control-plane";
import { redeployAction, rollbackAction } from "../actions";

export const dynamic = "force-dynamic";

const DEPLOYMENT_STAGES = [
  "queued",
  "preparing",
  "cloning",
  "building",
  "releasing",
  "health_check",
  "activating",
  "verifying",
  "succeeded",
] as const;

const ACTIVE_STATES = new Set([
  "queued",
  "preparing",
  "cloning",
  "building",
  "releasing",
  "health_check",
  "activating",
  "verifying",
]);

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
}

function formatDuration(start: string | null | undefined, end: string | null | undefined) {
  if (!start) return "—";
  const milliseconds = Math.max(0, new Date(end ?? Date.now()).getTime() - new Date(start).getTime());
  const seconds = Math.floor(milliseconds / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function stateTone(state: string) {
  if (state === "succeeded") return "success";
  if (state === "failed") return "danger";
  if (state === "rolled_back") return "warning";
  if (ACTIVE_STATES.has(state)) return "warning";
  return "neutral";
}

function stageStatus(stage: string, progressState: string) {
  const currentIndex = DEPLOYMENT_STAGES.indexOf(progressState as (typeof DEPLOYMENT_STAGES)[number]);
  const stageIndex = DEPLOYMENT_STAGES.indexOf(stage as (typeof DEPLOYMENT_STAGES)[number]);
  if (currentIndex < 0) return "pending";
  if (stageIndex < currentIndex) return "complete";
  if (stageIndex === currentIndex) return progressState === "succeeded" ? "complete" : "current";
  return "pending";
}

function findDiskWarning(events: Array<{ metadata?: Record<string, unknown> }> = []) {
  for (const event of [...events].reverse()) {
    const metadata = event.metadata ?? {};
    for (const [key, value] of Object.entries(metadata)) {
      if (key.toLowerCase().includes("disk") && (typeof value === "string" || typeof value === "number")) {
        return `${key.replaceAll("_", " ")}: ${String(value)}`;
      }
    }
  }
  return null;
}

export default async function DeploymentPage({
  params,
}: {
  params: Promise<{ deploymentId: string }>;
}) {
  const { deploymentId } = await params;
  const deployment = await getDeployment(deploymentId);
  const active = ACTIVE_STATES.has(deployment.state);
  const events = deployment.events ?? [];
  const diskWarning = findDiskWarning(events);
  const lastProgressEvent = [...events].reverse().find((event) =>
    DEPLOYMENT_STAGES.includes(event.state as (typeof DEPLOYMENT_STAGES)[number]),
  );
  const progressState =
    deployment.state === "failed" || deployment.state === "rolled_back"
      ? lastProgressEvent?.state ?? "queued"
      : deployment.state;
  const operationError = deployment.operation?.error_message || deployment.operation?.error_code;
  const failureEvent = [...events].reverse().find((event) => event.state === "failed");
  const errorMessage = operationError || failureEvent?.message || null;
  const canRedeploy = !active && Boolean(deployment.resolved_commit);
  const canRollback = !active && Boolean(deployment.previous_release || deployment.active_release);

  return (
    <main className="page deploymentConsole">
      <DeploymentLiveRefresh active={active} />

      <header className="pageHeader deploymentConsoleHeader">
        <div>
          <div className="deploymentTitleLine">
            <p className="eyebrow">DEPLOYMENT CONSOLE</p>
            <span className={`statusBadge status-${stateTone(deployment.state)}`}>
              <i className="statusIndicator" />
              {deployment.state}
            </span>
          </div>
          <h1>
            {deployment.state === "succeeded"
              ? "Deployment completed"
              : deployment.state === "failed"
                ? "Deployment failed"
                : deployment.state === "rolled_back"
                  ? "Deployment rolled back"
                  : "Deployment in progress"}
          </h1>
          <p className="pageLead">
            <code>{deployment.resolved_commit || deployment.requested_ref || "No commit resolved"}</code>
          </p>
        </div>

        <div className="pageActions">
          <form action={redeployAction}>
            <input type="hidden" name="deployment_id" value={deployment.id} />
            <button disabled={!canRedeploy}>Redeploy</button>
          </form>
          <form action={rollbackAction}>
            <input type="hidden" name="deployment_id" value={deployment.id} />
            <button disabled={!canRollback}>Rollback</button>
          </form>
        </div>
      </header>

      {diskWarning ? <div className="deploymentWarning">Disk warning · {diskWarning}</div> : null}
      {errorMessage ? (
        <section className="deploymentError" role="alert">
          <strong>{deployment.operation?.error_code || "Deployment failed"}</strong>
          <span>{errorMessage}</span>
        </section>
      ) : null}

      <section className="panel deploymentProgressPanel">
        <div className="panelHeader">
          <div>
            <h2>Progress</h2>
            <p>Live deployment lifecycle from queue to verification.</p>
          </div>
          <strong className="deploymentDuration">
            {formatDuration(deployment.started_at ?? deployment.queued_at, deployment.completed_at)}
          </strong>
        </div>
        <div className="deploymentStageTrack" aria-label="Deployment progress">
          {DEPLOYMENT_STAGES.map((stage) => {
            const status = stageStatus(stage, progressState);
            return (
              <div className={`deploymentStage deploymentStage-${status}`} key={stage}>
                <span className="deploymentStageDot" />
                <strong>{stage.replaceAll("_", " ")}</strong>
              </div>
            );
          })}
        </div>
        {deployment.state === "failed" || deployment.state === "rolled_back" ? (
          <div className={`deploymentTerminalState deploymentTerminalState-${deployment.state}`}>
            {deployment.state}
          </div>
        ) : null}
      </section>

      <div className="deploymentConsoleGrid">
        <section className="panel">
          <div className="panelHeader">
            <div>
              <h2>Deployment</h2>
              <p>Release and request metadata.</p>
            </div>
          </div>
          <div className="deploymentFacts">
            <div><span>Deployment ID</span><code>{deployment.id}</code></div>
            <div><span>Commit</span><code>{deployment.resolved_commit || deployment.requested_ref || "—"}</code></div>
            <div><span>Requested by</span><strong>{deployment.requested_by || "—"}</strong></div>
            <div><span>Queued</span><strong>{formatDate(deployment.queued_at)}</strong></div>
            <div><span>Started</span><strong>{formatDate(deployment.started_at)}</strong></div>
            <div><span>Completed</span><strong>{formatDate(deployment.completed_at)}</strong></div>
            <div><span>Active release</span><code>{deployment.active_release ?? "—"}</code></div>
            <div><span>Previous release</span><code>{deployment.previous_release ?? "—"}</code></div>
          </div>
        </section>

        <section className="panel">
          <div className="panelHeader">
            <div>
              <h2>Operation</h2>
              <p>Secondary execution state from the Agent queue.</p>
            </div>
          </div>
          <div className="deploymentFacts">
            <div><span>Operation ID</span><code>{deployment.operation?.id || deployment.operation_id || "—"}</code></div>
            <div><span>State</span><strong>{deployment.operation?.state || "—"}</strong></div>
            <div><span>Claimed</span><strong>{formatDate(deployment.operation?.claimed_at)}</strong></div>
            <div><span>Started</span><strong>{formatDate(deployment.operation?.started_at)}</strong></div>
            <div><span>Completed</span><strong>{formatDate(deployment.operation?.completed_at)}</strong></div>
            <div><span>Error code</span><code>{deployment.operation?.error_code || "—"}</code></div>
          </div>
        </section>
      </div>

      <section className="panel deploymentEventsPanel">
        <div className="panelHeader">
          <div>
            <h2>Event timeline</h2>
            <p>{events.length} recorded deployment events.</p>
          </div>
        </div>
        {events.length ? (
          <div className="deploymentTimeline">
            {[...events].reverse().map((event) => (
              <article className="deploymentTimelineRow" key={event.id}>
                <span className={`deploymentEventDot deploymentEventDot-${stateTone(event.state)}`} />
                <div>
                  <div className="deploymentEventHeader">
                    <code>{event.state}</code>
                    <time>{formatDate(event.created_at)}</time>
                  </div>
                  <p>{event.message || "State updated."}</p>
                  {event.metadata && Object.keys(event.metadata).length ? (
                    <details>
                      <summary>Technical metadata</summary>
                      <pre>{JSON.stringify(event.metadata, null, 2)}</pre>
                    </details>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="emptyState">
            <strong>No deployment events yet</strong>
            <p>The console will refresh automatically while the deployment is active.</p>
          </div>
        )}
      </section>
    </main>
  );
}
