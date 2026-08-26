import { Pool } from "pg";
import { dashboardConfig } from "./config";

const globalForDb = globalThis as unknown as { wpAgentPool?: Pool };

export const db = globalForDb.wpAgentPool ?? new Pool({
  connectionString: dashboardConfig.databaseUrl,
  max: 10,
});

if (process.env.NODE_ENV !== "production") globalForDb.wpAgentPool = db;

export async function initializeDatabase() {
  await db.query(`
    CREATE TABLE IF NOT EXISTS wordpress_sites (
      id UUID PRIMARY KEY,
      name VARCHAR(160) NOT NULL,
      base_url TEXT NOT NULL UNIQUE,
      username VARCHAR(160) NOT NULL,
      encrypted_app_password TEXT NOT NULL,
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
      last_check_status VARCHAR(32),
      last_check_message TEXT,
      last_checked_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS audit_logs (
      id BIGSERIAL PRIMARY KEY,
      site_id UUID REFERENCES wordpress_sites(id) ON DELETE SET NULL,
      action VARCHAR(100) NOT NULL,
      details JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  `);
}
