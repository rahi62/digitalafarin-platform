import type { WordPressConnection } from "./sites";

export type ThemeAutomationPolicy = {
  enabled: boolean;
  fullFileWriteEnabled: boolean;
  allowedFiles: string[];
  allowedDirectories: string[];
  maxFileBytes: number;
  backupRetentionPerFile: number;
  autoRollbackOnQaFailure: boolean;
};

export type ThemeAutomationStatus = {
  theme: {
    name: string;
    stylesheet: string;
    version: string;
    childTheme: boolean;
  };
  policy: ThemeAutomationPolicy;
  capabilities: {
    phpLint: boolean;
    atomicRename: boolean;
    backup: boolean;
    httpQa: boolean;
  };
  zipFallbackRecommended: boolean;
};

export type ThemeAutomationPolicyEnvelope = {
  policy: ThemeAutomationPolicy;
  hardDeniedFiles: string[];
  limits?: {
    maxFileBytes?: number;
    maxBackupRetentionPerFile?: number;
  };
  updated?: boolean;
};

type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
};

function authorization(connection: WordPressConnection) {
  return `Basic ${Buffer.from(
    `${connection.username}:${connection.appPassword.replace(/\s+/g, "")}`,
    "utf8",
  ).toString("base64")}`;
}

async function requestBridge<T>(
  connection: WordPressConnection,
  route: string,
  options: RequestOptions = {},
): Promise<T> {
  const url = new URL(`/wp-json/digitalafarin/v1/theme/${route.replace(/^\//, "")}`, connection.baseUrl);
  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers: {
      Authorization: authorization(connection),
      Accept: "application/json",
      "Content-Type": "application/json; charset=utf-8",
      "User-Agent": "DigitalAfarin-WP-Agent-Dashboard/0.3",
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
    signal: AbortSignal.timeout(20_000),
  });

  const raw = await response.text();
  let data: unknown;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    throw new Error(`Agent Bridge پاسخ JSON معتبر نداد (HTTP ${response.status}).`);
  }

  if (!response.ok) {
    const error = data as { message?: string; code?: string; data?: { errors?: string[] } } | null;
    const extra = error?.data?.errors?.length ? `: ${error.data.errors.join("، ")}` : "";
    throw new Error(`${error?.message ?? `Agent Bridge HTTP ${response.status}`}${extra}`);
  }
  return data as T;
}

export function getThemeAutomationStatus(connection: WordPressConnection) {
  return requestBridge<ThemeAutomationStatus>(connection, "status");
}

export function getThemeAutomationPolicy(connection: WordPressConnection) {
  return requestBridge<ThemeAutomationPolicyEnvelope>(connection, "policy");
}

export function updateThemeAutomationPolicy(
  connection: WordPressConnection,
  input: ThemeAutomationPolicy,
) {
  return requestBridge<ThemeAutomationPolicyEnvelope>(connection, "policy", {
    method: "POST",
    body: input,
  });
}
