import { WordPressError } from "./wordpress.js";

type WordPressConnection = { baseUrl: string; username: string; appPassword: string };
type RequestOptions = { method?: "GET" | "POST"; query?: Record<string, string | number | undefined>; body?: unknown };

export type ThemeBridgeErrorDetails = {
  zipFallbackRecommended?: boolean;
  blockReasons?: string[];
  reason?: string;
  errors?: string[];
  [key: string]: unknown;
};

export class ThemeTemplateError extends WordPressError {
  constructor(message: string, status: number, code?: string, readonly details?: ThemeBridgeErrorDetails) {
    super(message, status, code);
    this.name = "ThemeTemplateError";
  }
}

export type ThemeTemplateUpdateInput = {
  pageId: number;
  relativePath: string;
  expectedHash: string;
  proposedHash: string;
  replacementContent: string;
  qaNeedles?: string[];
};

export class ThemeTemplateClient {
  private readonly baseUrl: string;
  private readonly authorization: string;

  constructor(connection: WordPressConnection) {
    this.baseUrl = connection.baseUrl.replace(/\/$/, "");
    this.authorization = `Basic ${Buffer.from(
      `${connection.username}:${connection.appPassword.replace(/\s+/g, "")}`,
      "utf8",
    ).toString("base64")}`;
  }

  private async request<T>(route: string, options: RequestOptions = {}): Promise<T> {
    const url = new URL(`/wp-json/digitalafarin/v1/theme/${route.replace(/^\//, "")}`, this.baseUrl);
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
    const response = await fetch(url, {
      method: options.method ?? "GET",
      headers: {
        Authorization: this.authorization,
        Accept: "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "DigitalAfarin-WordPress-MCP/0.8",
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: AbortSignal.timeout(30_000),
    });
    const raw = await response.text();
    let data: unknown;
    try {
      data = raw ? JSON.parse(raw) : null;
    } catch {
      throw new ThemeTemplateError("WordPress returned a non-JSON response", response.status);
    }
    if (!response.ok) {
      const error = data as { code?: string; message?: string; data?: ThemeBridgeErrorDetails } | null;
      throw new ThemeTemplateError(
        error?.message || `WordPress request failed with HTTP ${response.status}`,
        response.status,
        error?.code,
        error?.data,
      );
    }
    return data as T;
  }

  getStatus() {
    return this.request<Record<string, unknown>>("status");
  }

  resolve(input: { pageId?: number; url?: string }) {
    return this.request<Record<string, unknown>>("resolve-template", { method: "POST", body: input });
  }

  read(relativePath: string) {
    return this.request<Record<string, unknown>>("file", { query: { relativePath } });
  }

  preview(input: { pageId: number; relativePath: string; expectedHash: string; replacementContent: string }) {
    this.assertHash(input.expectedHash, "expectedHash");
    return this.request<Record<string, unknown>>("file/preview", { method: "POST", body: input });
  }

  update(input: ThemeTemplateUpdateInput) {
    this.assertHash(input.expectedHash, "expectedHash");
    this.assertHash(input.proposedHash, "proposedHash");
    if (!input.replacementContent) throw new Error("replacementContent is required");
    return this.request<Record<string, unknown>>("file/update", { method: "POST", body: input });
  }

  listBackups(relativePath?: string, limit = 50) {
    return this.request<{ backups: unknown[] }>("backups", { query: { relativePath, limit } });
  }

  restoreBackup(backupId: string, expectedCurrentHash: string) {
    this.assertHash(expectedCurrentHash, "expectedCurrentHash");
    if (!/^[a-f0-9-]{36}$/i.test(backupId)) throw new Error("backupId must be a UUID");
    return this.request<Record<string, unknown>>(`backups/${backupId}/restore`, {
      method: "POST",
      body: { expectedCurrentHash },
    });
  }

  private assertHash(value: string, field: string) {
    if (!/^[a-f0-9]{64}$/i.test(value)) {
      throw new Error(`${field} must be a 64-character SHA-256 hash`);
    }
  }
}
