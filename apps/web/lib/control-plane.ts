import "server-only";
import { buildServiceOperation, type ServiceAction } from "./operations";
import { buildDeployRequest, projectPath } from "./deployments";

export type ServerStatus = "online" | "stale" | "offline" | string;

export type ServerSummary = {
  id: string;
  name: string;
  hostname: string;
  is_default: boolean;
  status: ServerStatus;
  last_seen_at: string | null;
  age_seconds: number | null;
  agent_version: string;
  capabilities: string[];
};

export type MetricsSnapshot = {
  id: string;
  name: string;
  status: ServerStatus;
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  uptime_seconds: number;
  collected_at: string | null;
  age_seconds: number | null;
  stale: boolean;
};

export type ServiceSnapshot = {
  unit_name: string;
  description: string;
  load_state: string;
  active_state: string;
  sub_state: string;
  last_seen_at: string;
};

export type AuditEvent = {
  event_type: string;
  target_type: string;
  target_id: string;
  actor: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type Operation = {
  id: string;
  server_id: string;
  kind: "service.start" | "service.stop" | "service.restart" | "service.logs";
  state: "queued" | "claimed" | "running" | "succeeded" | "failed";
  payload: { unit_name: string; lines?: number; since_seconds?: number };
  result?: { message?: string; logs?: string; truncated?: boolean };
  error_code: string;
  error_message: string;
  actor: string;
  created_at: string;
  claimed_at: string | null;
  started_at: string | null;
  completed_at: string | null;
};

export type ManagedService = {
  id: string; project_id: string; name: string; executor: "systemd";
  repository: string; branch: string; root_directory: string;
  runtime: "node-nextjs" | "python-django"; service_port: number; target_server_id: string;
};

export type Project = {
  id: string; name: string; slug: string;
  services?: ManagedService[];
  variables?: Array<{ id: string; key: string; value_type: "plain" | "secret"; scope: string; has_value: boolean; value?: string }>;
  volumes?: Array<{ id: string; name: string; host_path: string; mount_path: string }>;
  databases?: Array<{ id: string; database_name: string; username: string; status: string; has_credential: boolean }>;
  domains?: Array<{ id: string; hostname: string; status: string; ssl_enabled: boolean }>;
};

export type Deployment = {
  id: string; service_id: string; requested_ref: string; resolved_commit: string;
  state: string; requested_by: string; queued_at: string; started_at: string | null;
  completed_at: string | null; active_release?: string | null; previous_release?: string | null;
  events?: Array<{ id: string; state: string; message: string; created_at: string }>;
};

export class ControlPlaneError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ControlPlaneError";
  }
}

function getConfig() {
  const baseUrl = (process.env.PLATFORM_API_URL ?? "http://127.0.0.1:9750").replace(/\/$/, "");
  const token = process.env.PLATFORM_API_TOKEN;
  if (!token) throw new Error("PLATFORM_API_TOKEN is not configured");
  return { baseUrl, token };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { baseUrl, token } = getConfig();
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
    cache: "no-store",
  });

  const body = await response.json().catch(() => ({})) as Record<string, unknown>;
  if (!response.ok) {
    throw new ControlPlaneError(
      response.status,
      typeof body.error === "string" ? body.error : "control_plane_error",
      typeof body.message === "string" ? body.message : `Control Plane returned HTTP ${response.status}`,
    );
  }
  return body as T;
}

function encodeServerId(serverId: string) {
  return encodeURIComponent(serverId || "default");
}

export async function listServers(): Promise<ServerSummary[]> {
  const result = await request<{ items: ServerSummary[] }>("/api/control/v1/servers/");
  return result.items;
}

export function getServer(serverId = "default"): Promise<ServerSummary> {
  return request(`/api/control/v1/servers/${encodeServerId(serverId)}/`);
}

export function getMetrics(serverId = "default"): Promise<MetricsSnapshot> {
  return request(`/api/control/v1/servers/${encodeServerId(serverId)}/metrics/`);
}

export async function listServices(serverId = "default", status?: string): Promise<ServiceSnapshot[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const result = await request<{ items: ServiceSnapshot[] }>(
    `/api/control/v1/servers/${encodeServerId(serverId)}/services/${query}`,
  );
  return result.items;
}

export function getService(serverId: string, unitName: string): Promise<ServiceSnapshot> {
  return request(
    `/api/control/v1/servers/${encodeServerId(serverId)}/services/${encodeURIComponent(unitName)}/`,
  );
}

export async function listAuditEvents(options: { serverId?: string; limit?: number } = {}): Promise<AuditEvent[]> {
  const params = new URLSearchParams();
  if (options.serverId && options.serverId !== "default") params.set("server_id", options.serverId);
  params.set("limit", String(Math.min(100, Math.max(1, options.limit ?? 20))));
  const result = await request<{ items: AuditEvent[] }>(`/api/control/v1/audit/?${params.toString()}`);
  return result.items;
}

export async function listOperations(): Promise<Operation[]> {
  const result = await request<{ items: Operation[] }>("/api/control/v1/operations/");
  return result.items;
}

export function getOperation(operationId: string): Promise<Operation> {
  return request(`/api/control/v1/operations/${encodeURIComponent(operationId)}/`);
}

export function createServiceOperation(
  serverId: string,
  action: ServiceAction,
  unitName: string,
  idempotencyKey: string,
): Promise<Operation> {
  return request("/api/control/v1/operations/", {
    method: "POST",
    body: JSON.stringify(buildServiceOperation(serverId, action, unitName, idempotencyKey)),
  });
}

export function createServiceLogsOperation(
  serverId: string,
  unitName: string,
  lines = 100,
  sinceSeconds = 3600,
): Promise<Operation> {
  return request("/api/control/v1/operations/", {
    method: "POST",
    body: JSON.stringify({
      server_id: serverId,
      kind: "service.logs",
      payload: { unit_name: unitName, lines, since_seconds: sinceSeconds },
    }),
  });
}

export async function listProjects(): Promise<Project[]> {
  const result = await request<{ items: Project[] }>("/api/control/v1/projects/");
  return result.items;
}

export function getProject(projectId: string): Promise<Project> {
  return request(projectPath(projectId));
}

export async function listDeployments(serviceId: string): Promise<Deployment[]> {
  const result = await request<{ items: Deployment[] }>(`/api/control/v1/services/${encodeURIComponent(serviceId)}/deployments/`);
  return result.items;
}

export function getDeployment(deploymentId: string): Promise<Deployment> {
  return request(`/api/control/v1/deployments/${encodeURIComponent(deploymentId)}/`);
}

export function deployService(serviceId: string, commit?: string): Promise<Deployment> {
  return request(`/api/control/v1/services/${encodeURIComponent(serviceId)}/deployments/`, {
    method: "POST", body: JSON.stringify(buildDeployRequest(commit)),
  });
}

export function redeployDeployment(deploymentId: string): Promise<Deployment> {
  return request(`/api/control/v1/deployments/${encodeURIComponent(deploymentId)}/redeploy/`, { method: "POST", body: "{}" });
}

export function rollbackDeployment(deploymentId: string): Promise<Deployment> {
  return request(`/api/control/v1/deployments/${encodeURIComponent(deploymentId)}/rollback/`, { method: "POST", body: "{}" });
}
