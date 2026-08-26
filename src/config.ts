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

const siteBrokerUrl = (process.env.SITE_BROKER_URL?.trim() || "http://127.0.0.1:3040/api/internal/sites").replace(/\/$/, "");
if (!siteBrokerUrl.startsWith("http://127.0.0.1:") && !siteBrokerUrl.startsWith("http://localhost:")) {
  throw new Error("SITE_BROKER_URL must point to a loopback HTTP endpoint");
}

export const config = {
  siteBrokerUrl,
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
