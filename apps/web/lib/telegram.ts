import "server-only";

export type TelegramStatus = {
  bot_configured: boolean;
  bot_name: string | null;
  bot_active: boolean;
  active_channels: number;
};

export type TelegramChannel = {
  id: string;
  alias: string;
  name: string;
  chat_id: string;
  is_active: boolean;
  description: string;
  created_at: string;
  updated_at: string;
};

export type TelegramAudit = {
  id: string;
  channel: string | null;
  action: "test" | "publish" | string;
  status: "success" | "failed" | string;
  message_ids: number[];
  content_preview: string;
  error_code: string;
  error_message: string;
  actor_principal: string;
  created_at: string;
};

export class TelegramControlPlaneError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "TelegramControlPlaneError";
  }
}

function getConfig() {
  const baseUrl = (process.env.PLATFORM_API_URL ?? "http://127.0.0.1:9750").replace(/\/$/, "");
  const token = process.env.TELEGRAM_PLATFORM_API_TOKEN;
  if (!token) throw new Error("TELEGRAM_PLATFORM_API_TOKEN is not configured");
  return { baseUrl, token };
}

async function request<T>(
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  const { baseUrl, token } = getConfig();
  const response = await fetch(`${baseUrl}${path}`, {
    method: init.method ?? "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      ...(init.body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    cache: "no-store",
  });

  const body = await response.json().catch(() => ({})) as Record<string, unknown>;
  if (!response.ok) {
    throw new TelegramControlPlaneError(
      response.status,
      typeof body.error === "string" ? body.error : "telegram_control_plane_error",
      typeof body.message === "string" ? body.message : `Control Plane returned HTTP ${response.status}`,
    );
  }
  return body as T;
}

export function getTelegramStatus(): Promise<TelegramStatus> {
  return request("/api/control/v1/telegram/status/");
}

export async function listTelegramChannels(): Promise<TelegramChannel[]> {
  const result = await request<{ items: TelegramChannel[] }>("/api/control/v1/telegram/channels/");
  return result.items;
}

export async function listTelegramAudit(limit = 30): Promise<TelegramAudit[]> {
  const safeLimit = Math.max(1, Math.min(limit, 100));
  const result = await request<{ items: TelegramAudit[] }>(
    `/api/control/v1/telegram/audit/?limit=${safeLimit}`,
  );
  return result.items;
}

export function setTelegramCredential(input: { token: string; name?: string }) {
  return request<{ configured: boolean; name: string; bot_id?: number; bot_username?: string }>(
    "/api/control/v1/telegram/bot-credential/",
    { method: "PUT", body: input },
  );
}

export function createTelegramChannel(input: {
  alias: string;
  name: string;
  chat_id: string;
  description?: string;
  is_active?: boolean;
}) {
  return request<TelegramChannel>("/api/control/v1/telegram/channels/", {
    method: "POST",
    body: input,
  });
}

export function updateTelegramChannel(
  id: string,
  input: Partial<Pick<TelegramChannel, "alias" | "name" | "chat_id" | "description" | "is_active">>,
) {
  return request<TelegramChannel>(`/api/control/v1/telegram/channels/${encodeURIComponent(id)}/`, {
    method: "PATCH",
    body: input,
  });
}

export function testTelegramChannel(id: string) {
  return request<{ ok: boolean; channel: string; message_ids: number[] }>(
    `/api/control/v1/telegram/channels/${encodeURIComponent(id)}/test/`,
    { method: "POST", body: {} },
  );
}
