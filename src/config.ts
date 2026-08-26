import "dotenv/config";

function positiveInteger(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number.parseInt(raw, 10);
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }
  return value;
}

function loopbackBroker(name: string, value: string) {
  const normalized = value.replace(/\/$/, "");
  if (!normalized.startsWith("http://127.0.0.1:") && !normalized.startsWith("http://localhost:")) {
    throw new Error(`${name} must point to a loopback HTTP endpoint`);
  }
  return normalized;
}

const siteBrokerUrl = loopbackBroker(
  "SITE_BROKER_URL",
  process.env.SITE_BROKER_URL?.trim() || "http://127.0.0.1:3040/api/internal/sites",
);
const gscBrokerUrl = loopbackBroker(
  "GSC_BROKER_URL",
  process.env.GSC_BROKER_URL?.trim() || "http://127.0.0.1:3040/api/internal/gsc",
);

export const config = {
  siteBrokerUrl,
  gscBrokerUrl,
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
  maxMediaBytes: positiveInteger("MAX_MEDIA_BYTES", 10_000_000),
};
