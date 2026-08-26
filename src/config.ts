import "dotenv/config";

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

function positiveInteger(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number.parseInt(raw, 10);
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }
  return value;
}

const baseUrl = required("WP_BASE_URL").replace(/\/$/, "");
if (!baseUrl.startsWith("https://")) {
  throw new Error("WP_BASE_URL must use HTTPS");
}

export const config = {
  wpBaseUrl: baseUrl,
  wpUsername: required("WP_USERNAME"),
  wpAppPassword: required("WP_APP_PASSWORD").replace(/\s+/g, ""),
  port: positiveInteger("PORT", 3030),
  host: process.env.HOST?.trim() || "127.0.0.1",
  allowedOrigins: new Set(
    (process.env.ALLOWED_ORIGINS || "https://chatgpt.com")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  ),
  bearerToken: process.env.MCP_BEARER_TOKEN?.trim() || undefined,
  maxPostContentBytes: positiveInteger("MAX_POST_CONTENT_BYTES", 500_000),
};
