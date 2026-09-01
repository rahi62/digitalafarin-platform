export type Service = {
  id: number;
  unit_name: string;
  description: string;
  load_state: string;
  active_state: string;
  sub_state: string;
  last_seen_at: string;
};

export type Server = {
  id: number;
  name: string;
  hostname: string;
  agent_url: string;
  is_active: boolean;
  last_seen_at: string | null;
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  uptime_seconds: number;
  services: Service[];
};

function config() {
  const baseUrl = process.env.PLATFORM_API_URL ?? "http://127.0.0.1:8000";
  const token = process.env.PLATFORM_API_TOKEN;
  if (!token) throw new Error("PLATFORM_API_TOKEN is not configured");
  return { baseUrl: baseUrl.replace(/\/$/, ""), token };
}

export async function getServer(): Promise<Server | null> {
  const { baseUrl, token } = config();
  const id = process.env.PLATFORM_SERVER_ID ?? "1";
  try {
    const response = await fetch(`${baseUrl}/api/servers/${id}/`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

export async function syncServer(): Promise<Response> {
  const { baseUrl, token } = config();
  const id = process.env.PLATFORM_SERVER_ID ?? "1";
  return fetch(`${baseUrl}/api/servers/${id}/sync/`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    cache: "no-store",
  });
}
