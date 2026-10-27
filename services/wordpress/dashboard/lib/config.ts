import { createHash } from "node:crypto";

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

/**
 * Keep validation strict at use-time, without evaluating runtime credentials
 * during Next.js's build-time route discovery.
 */
export const dashboardConfig = {
  get databaseUrl(): string { return required("DATABASE_URL"); },
  get adminPasswordHash(): string { return required("ADMIN_PASSWORD_SHA256").toLowerCase(); },
  get sessionSecret(): string { return required("SESSION_SECRET"); },
  get encryptionKey(): Buffer {
    const key = Buffer.from(required("CREDENTIALS_ENCRYPTION_KEY"), "base64");
    if (key.length !== 32) throw new Error("CREDENTIALS_ENCRYPTION_KEY must decode to exactly 32 bytes");
    return key;
  },
};

export function passwordDigest(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}
