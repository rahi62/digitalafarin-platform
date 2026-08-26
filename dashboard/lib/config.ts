import { createHash } from "node:crypto";

function required(name: string) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

function optional(name: string) {
  return process.env[name]?.trim() || undefined;
}

const googleClientId = optional("GSC_GOOGLE_CLIENT_ID");
const googleClientSecret = optional("GSC_GOOGLE_CLIENT_SECRET");
const googleRedirectUri = optional("GSC_GOOGLE_REDIRECT_URI");

export const dashboardConfig = {
  databaseUrl: required("DATABASE_URL"),
  adminPasswordHash: required("ADMIN_PASSWORD_SHA256").toLowerCase(),
  sessionSecret: required("SESSION_SECRET"),
  encryptionKey: Buffer.from(required("CREDENTIALS_ENCRYPTION_KEY"), "base64"),
  googleClientId,
  googleClientSecret,
  googleRedirectUri,
  gscOAuthConfigured: Boolean(googleClientId && googleClientSecret && googleRedirectUri),
};

if (dashboardConfig.encryptionKey.length !== 32) {
  throw new Error("CREDENTIALS_ENCRYPTION_KEY must decode to exactly 32 bytes");
}

export function passwordDigest(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}
