import "server-only";

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

async function request<T>(path: string): Promise<T> {
  const { baseUrl, token } = getConfig();
  const response = await fetch(`${baseUrl}${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
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
