import { decryptSecret } from "./crypto";
import { db, initializeDatabase } from "./db";

export type DashboardSite = {
  id: string;
  name: string;
  base_url: string;
  username: string;
  enabled: boolean;
  last_check_status: string | null;
  last_check_message: string | null;
  last_checked_at: Date | null;
};

export type WordPressConnection = {
  id: string;
  name: string;
  baseUrl: string;
  username: string;
  appPassword: string;
};

export async function listSites(enabledOnly = false) {
  await initializeDatabase();
  const result = await db.query<DashboardSite>(
    `SELECT id,name,base_url,username,enabled,last_check_status,last_check_message,last_checked_at
     FROM wordpress_sites
     ${enabledOnly ? "WHERE enabled=TRUE" : ""}
     ORDER BY created_at DESC`,
  );
  return result.rows;
}

export async function getSiteConnection(siteId: string): Promise<WordPressConnection> {
  await initializeDatabase();
  const result = await db.query<{
    id: string; name: string; base_url: string; username: string; encrypted_app_password: string; enabled: boolean;
  }>(
    `SELECT id,name,base_url,username,encrypted_app_password,enabled
     FROM wordpress_sites WHERE id=$1 LIMIT 1`,
    [siteId],
  );
  const site = result.rows[0];
  if (!site) throw new Error("سایت انتخاب‌شده پیدا نشد.");
  if (!site.enabled) throw new Error("سایت انتخاب‌شده غیرفعال است.");
  return {
    id: site.id,
    name: site.name,
    baseUrl: site.base_url,
    username: site.username,
    appPassword: decryptSecret(site.encrypted_app_password),
  };
}
