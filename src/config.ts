import "dotenv/config";
import path from "node:path";

const allowedOrigins = new Set(
  (process.env.ALLOWED_ORIGINS ?? "https://chatgpt.com")
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean),
);

export const config = {
  host: process.env.HOST ?? "127.0.0.1",
  port: Number(process.env.PORT ?? 3050),
  bearerToken: (process.env.BEARER_TOKEN ?? "").trim(),
  allowedOrigins,
  dataFile: path.resolve(process.env.DATA_FILE ?? "./data/agency.json"),
};
