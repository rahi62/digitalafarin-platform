export type ReadinessState = "ready" | "warning" | "pending" | "blocked";
export type ReadinessStep = { label: string; state: ReadinessState; detail: string };

export type MigrationServerInput = { id?: string; status: string };
export type MigrationProjectInput = {
  services?: Array<{ id: string; runtime?: string; target_server_id?: string }>;
  variables?: Array<{ id: string; value_type: string; has_value: boolean }>;
  volumes?: Array<{ id: string }>;
  databases?: Array<{ id: string; status: string }>;
  domains?: Array<{ id: string; status?: string; ssl_enabled: boolean }>;
};
export type MigrationReadinessContext = {
  operations?: Array<{ server_id: string; kind: string; state: string; created_at?: string }>;
  deployments?: Array<{ service_id: string; state: string; queued_at?: string }>;
  metrics?: Array<{ id: string; disk_percent: number; stale: boolean }>;
  selectedProjectId?: string;
  projectCount?: number;
};

function diskReadiness(metrics: NonNullable<MigrationReadinessContext["metrics"]>): Pick<ReadinessStep, "state" | "detail"> {
  if (metrics.length === 0 || metrics.some((item) => item.stale)) {
    return { state: "blocked", detail: "Disk telemetry is missing or stale" };
  }
  const highest = Math.max(...metrics.map((item) => item.disk_percent));
  if (highest >= 90) return { state: "blocked", detail: `${highest}% used; deployments blocked` };
  if (highest >= 80) return { state: "warning", detail: `${highest}% used; cleanup recommended` };
  return { state: "ready", detail: `${highest}% used` };
}

export function deriveMigrationReadiness(
  servers: MigrationServerInput[],
  projects: MigrationProjectInput[],
  context: MigrationReadinessContext = {},
): ReadinessStep[] {
  const services = projects.flatMap((project) => project.services ?? []);
  const variables = projects.flatMap((project) => project.variables ?? []);
  const volumes = projects.flatMap((project) => project.volumes ?? []);
  const databases = projects.flatMap((project) => project.databases ?? []);
  const domains = projects.flatMap((project) => project.domains ?? []);
  const operations = context.operations ?? [];
  const deployments = context.deployments ?? [];
  const targetServerIds = new Set(services.map((service) => service.target_server_id).filter((id): id is string => Boolean(id)));
  const targetServers = targetServerIds.size > 0
    ? servers.filter((server) => server.id && targetServerIds.has(server.id))
    : servers;
  const online = targetServers.length > 0 && targetServers.every((server) => server.status === "online");
  const backendServices = services.filter((item) => item.runtime === "python-django");
  const frontendServices = services.filter((item) => item.runtime === "node-nextjs");
  const newest = <T>(current: T | undefined, candidate: T, timestamp: (item: T) => string | undefined): T => {
    if (!current) return candidate;
    const currentTime = Date.parse(timestamp(current) ?? "");
    const candidateTime = Date.parse(timestamp(candidate) ?? "");
    if (Number.isNaN(candidateTime)) return current;
    if (Number.isNaN(currentTime) || candidateTime > currentTime) return candidate;
    return current;
  };
  const latestBootstrapByServer = new Map<string, (typeof operations)[number]>();
  for (const operation of operations.filter((item) => item.kind === "server.bootstrap")) {
    latestBootstrapByServer.set(
      operation.server_id,
      newest(latestBootstrapByServer.get(operation.server_id), operation, (item) => item.created_at),
    );
  }
  const bootstrapOperations = targetServerIds.size > 0
    ? [...targetServerIds].map((serverId) => latestBootstrapByServer.get(serverId))
    : [...latestBootstrapByServer.values()];
  const bootstrapState: Pick<ReadinessStep, "state" | "detail"> = bootstrapOperations.some((item) => item?.state === "failed")
    ? { state: "blocked", detail: "Latest typed bootstrap failed for a target server" }
    : bootstrapOperations.length > 0 && bootstrapOperations.every((item) => item?.state === "succeeded")
      ? { state: "ready", detail: "Latest typed bootstrap succeeded for every target server" }
      : { state: online ? "pending" : "blocked", detail: "Run typed readiness/bootstrap operation for every target server" };
  const latestDeploymentByService = new Map<string, (typeof deployments)[number]>();
  for (const deployment of deployments) {
    latestDeploymentByService.set(
      deployment.service_id,
      newest(latestDeploymentByService.get(deployment.service_id), deployment, (item) => item.queued_at),
    );
  }
  const deploymentReadiness = (selectedServices: typeof services): Pick<ReadinessStep, "state" | "detail"> => {
    if (selectedServices.length === 0) return { state: "pending", detail: "No matching service configured" };
    const latest = selectedServices.map((service) => latestDeploymentByService.get(service.id));
    const succeeded = latest.filter((deployment) => deployment?.state === "succeeded").length;
    if (latest.some((deployment) => deployment?.state === "failed" || deployment?.state === "rolled_back")) {
      return { state: "blocked", detail: "A latest deployment failed or was rolled back" };
    }
    return {
      state: succeeded === selectedServices.length ? "ready" : "pending",
      detail: `${succeeded}/${selectedServices.length} latest deployment(s) succeeded`,
    };
  };
  const scopedMetrics = targetServerIds.size > 0
    ? (context.metrics ?? []).filter((item) => targetServerIds.has(item.id))
    : (context.metrics ?? []);
  const ready = (condition: boolean, detail: string): Pick<ReadinessStep, "state" | "detail"> => ({ state: condition ? "ready" : "pending", detail });
  const heartbeatState: Pick<ReadinessStep, "state" | "detail"> = online
    ? { state: "ready", detail: "Every target agent is online" }
    : targetServers.length > 0
      ? { state: "blocked", detail: "A target agent heartbeat is stale or offline" }
      : { state: "pending", detail: "Awaiting fresh outbound heartbeat" };
  const projectCount = context.projectCount ?? projects.length;
  const projectSelected = Boolean(context.selectedProjectId) || (context.projectCount === undefined && projects.length > 0);
  const projectState: Pick<ReadinessStep, "state" | "detail"> = projectSelected
    ? { state: "ready", detail: `${projectCount} project(s); target selected` }
    : { state: "pending", detail: projectCount > 0 ? `${projectCount} project(s) available; select one` : "0 project(s)" };
  return [
    { label: "Enroll new VPS", ...ready(servers.length > 0, `${servers.length} server(s) enrolled`) },
    { label: "Heartbeat", ...heartbeatState },
    { label: "Bootstrap", ...bootstrapState },
    { label: "Select project", ...projectState },
    { label: "Create variables", ...ready(variables.length > 0 && variables.every((item) => item.value_type !== "secret" || item.has_value), `${variables.length} secret-safe variable metadata record(s)`) },
    { label: "Create volumes", ...ready(volumes.length > 0, `${volumes.length} volume(s)`) },
    { label: "Restore volume data", state: "pending", detail: "Operator verification required" },
    { label: "Create/restore PostgreSQL", ...ready(databases.some((item) => item.status === "ready"), `${databases.length} database(s)`) },
    { label: "Deploy backend", ...deploymentReadiness(backendServices) },
    { label: "Deploy frontend", ...deploymentReadiness(frontendServices) },
    { label: "Health check", ...deploymentReadiness(services) },
    { label: "Configure domains", ...ready(domains.some((item) => item.status === "configured"), `${domains.length} domain(s)`) },
    { label: "SSL", ...ready(domains.some((item) => item.ssl_enabled), "Typed Certbot workflow") },
    { label: "Disk guardrail", ...diskReadiness(scopedMetrics) },
    { label: "Final verification", state: "pending", detail: "Run production-safe checks" },
    { label: "DNS cutover", state: "pending", detail: "Manual external change" },
  ];
}
