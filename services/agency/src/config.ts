import "dotenv/config";
import path from "node:path";

const allowedOrigins = new Set(
  (process.env.ALLOWED_ORIGINS ?? "https://chatgpt.com")
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean),
);

const storeDriver = process.env.STORE_DRIVER === "postgres" ? "postgres" : "json";

export const config = {
  host: process.env.HOST ?? "127.0.0.1",
  port: Number(process.env.PORT ?? 3050),
  bearerToken: (process.env.BEARER_TOKEN ?? "").trim(),
  allowedOrigins,
  dataFile: path.resolve(process.env.DATA_FILE ?? "./data/agency.json"),
  storeDriver,
  databaseUrl: (process.env.DATABASE_URL ?? "").trim(),
  adminOrigin: (process.env.ADMIN_ORIGIN ?? "https://agency.digitalafarin.ir").trim(),
  sessionCookieName: (process.env.SESSION_COOKIE_NAME ?? "digitalafarin_agency_session").trim(),
  sessionTtlHours: Number(process.env.SESSION_TTL_HOURS ?? 168),
  csrfSecret: (process.env.CSRF_SECRET ?? "").trim(),
};
