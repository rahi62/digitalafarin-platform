export type ReadinessState = "ready" | "warning" | "pending" | "blocked";
export type ReadinessStep = { label: string; state: ReadinessState; detail: string };

type ServerInput = { id?: string; status: string };
type ProjectInput = {
  services?: Array<{ id: string; runtime?: string }>;
  variables?: Array<{ id: string; value_type: string; has_value: boolean }>;
  volumes?: Array<{ id: string }>;
  databases?: Array<{ id: string; status: string }>;
  domains?: Array<{ id: string; status?: string; ssl_enabled: boolean }>;
};
type ReadinessContext = {
  operations?: Array<{ server_id: string; kind: string; state: string }>;
  deployments?: Array<{ service_id: string; state: string }>;
  metrics?: Array<{ id: string; disk_percent: number; stale: boolean }>;
};

function diskReadiness(metrics: NonNullable<ReadinessContext["metrics"]>): Pick<ReadinessStep, "state" | "detail"> {
  if (metrics.length === 0 || metrics.some((item) => item.stale)) {
    return { state: "blocked", detail: "Disk telemetry is missing or stale" };
  }
  const highest = Math.max(...metrics.map((item) => item.disk_percent));
  if (highest >= 90) return { state: "blocked", detail: `${highest}% used; deployments blocked` };
  if (highest >= 80) return { state: "warning", detail: `${highest}% used; cleanup recommended` };
  return { state: "ready", detail: `${highest}% used` };
}

export function deriveMigrationReadiness(
  servers: ServerInput[],
  projects: ProjectInput[],
  context: ReadinessContext = {},
): ReadinessStep[] {
  const online = servers.some((server) => server.status === "online");
  const services = projects.flatMap((project) => project.services ?? []);
  const variables = projects.flatMap((project) => project.variables ?? []);
  const volumes = projects.flatMap((project) => project.volumes ?? []);
  const databases = projects.flatMap((project) => project.databases ?? []);
  const domains = projects.flatMap((project) => project.domains ?? []);
  const operations = context.operations ?? [];
  const deployments = context.deployments ?? [];
  const successfulServices = new Set(
    deployments.filter((item) => item.state === "succeeded").map((item) => item.service_id),
  );
  const backendServices = services.filter((item) => item.runtime === "python-django");
  const frontendServices = services.filter((item) => item.runtime === "node-nextjs");
  const latestBootstrap = operations.find((item) => item.kind === "server.bootstrap");
  const bootstrapState: Pick<ReadinessStep, "state" | "detail"> = latestBootstrap?.state === "succeeded"
    ? { state: "ready", detail: "Latest typed bootstrap succeeded" }
    : latestBootstrap?.state === "failed"
      ? { state: "blocked", detail: "Latest typed bootstrap failed" }
      : { state: online ? "pending" : "blocked", detail: "Run typed readiness/bootstrap operation" };
  const ready = (condition: boolean, detail: string): Pick<ReadinessStep, "state" | "detail"> => ({ state: condition ? "ready" : "pending", detail });
  return [
    { label: "Enroll new VPS", ...ready(servers.length > 0, `${servers.length} server(s) enrolled`) },
    { label: "Heartbeat", ...ready(online, online ? "Agent online" : "Awaiting fresh outbound heartbeat") },
    { label: "Bootstrap", ...bootstrapState },
    { label: "Select project", ...ready(projects.length > 0, `${projects.length} project(s)`) },
    { label: "Create variables", ...ready(variables.length > 0 && variables.every((item) => item.value_type !== "secret" || item.has_value), `${variables.length} secret-safe variable metadata record(s)`) },
    { label: "Create volumes", ...ready(volumes.length > 0, `${volumes.length} volume(s)`) },
    { label: "Restore volume data", state: "pending", detail: "Operator verification required" },
    { label: "Create/restore PostgreSQL", ...ready(databases.some((item) => item.status === "ready"), `${databases.length} database(s)`) },
    { label: "Deploy backend", ...ready(backendServices.some((item) => successfulServices.has(item.id)) || (backendServices.length === 0 && successfulServices.size > 0), `${successfulServices.size} service(s) successfully deployed`) },
    { label: "Deploy frontend", ...ready(frontendServices.some((item) => successfulServices.has(item.id)) || (frontendServices.length === 0 && successfulServices.size >= 2), `${successfulServices.size} service(s) successfully deployed`) },
    { label: "Health check", ...ready(successfulServices.size > 0, "Derived from successful deployment verification") },
    { label: "Configure domains", ...ready(domains.some((item) => item.status === "configured"), `${domains.length} domain(s)`) },
    { label: "SSL", ...ready(domains.some((item) => item.ssl_enabled), "Typed Certbot workflow") },
    { label: "Disk guardrail", ...diskReadiness(context.metrics ?? []) },
    { label: "Final verification", state: "pending", detail: "Run production-safe checks" },
    { label: "DNS cutover", state: "pending", detail: "Manual external change" },
  ];
}
