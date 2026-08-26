import { createHash } from "node:crypto";

function required(name: string) {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

export const dashboardConfig = {
  databaseUrl: required("DATABASE_URL"),
  adminPasswordHash: required("ADMIN_PASSWORD_SHA256").toLowerCase(),
  sessionSecret: required("SESSION_SECRET"),
  encryptionKey: Buffer.from(required("CREDENTIALS_ENCRYPTION_KEY"), "base64"),
};

if (dashboardConfig.encryptionKey.length !== 32) {
  throw new Error("CREDENTIALS_ENCRYPTION_KEY must decode to exactly 32 bytes");
}

export function passwordDigest(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}
