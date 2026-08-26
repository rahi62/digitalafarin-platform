import { decryptSecret, encryptSecret } from "./crypto";
import { db, initializeDatabase } from "./db";

const GSC_PROVIDER = "google-search-console";

type IntegrationRow = {
  config: Record<string, unknown>;
  encrypted_secret: string | null;
  updated_at: Date;
};

export type GscOAuthAppStatus = {
  configured: boolean;
  clientId: string;
  hasClientSecret: boolean;
  updatedAt: Date | null;
};

export async function getGscOAuthAppStatus(): Promise<GscOAuthAppStatus> {
  await initializeDatabase();
  const result = await db.query<IntegrationRow>(
    "SELECT config,encrypted_secret,updated_at FROM integration_configs WHERE provider=$1 LIMIT 1",
    [GSC_PROVIDER],
  );
  const row = result.rows[0];
  const clientId = typeof row?.config?.clientId === "string" ? row.config.clientId.trim() : "";
  return {
    configured: Boolean(clientId && row?.encrypted_secret),
    clientId,
    hasClientSecret: Boolean(row?.encrypted_secret),
    updatedAt: row?.updated_at ?? null,
  };
}

export async function getGscOAuthCredentials() {
  await initializeDatabase();
  const result = await db.query<IntegrationRow>(
    "SELECT config,encrypted_secret,updated_at FROM integration_configs WHERE provider=$1 LIMIT 1",
    [GSC_PROVIDER],
  );
  const row = result.rows[0];
  const clientId = typeof row?.config?.clientId === "string" ? row.config.clientId.trim() : "";
  if (!clientId || !row?.encrypted_secret) {
    throw new Error("Google OAuth App هنوز در تنظیمات پنل پیکربندی نشده است.");
  }
  return {
    clientId,
    clientSecret: decryptSecret(row.encrypted_secret),
  };
}

export async function saveGscOAuthCredentials(input: { clientId: string; clientSecret?: string }) {
  await initializeDatabase();
  const clientId = input.clientId.trim();
  if (!clientId) throw new Error("Google Client ID الزامی است.");

  const client = await db.connect();
  try {
    await client.query("BEGIN");
    const existing = await client.query<{ encrypted_secret: string | null; config: Record<string, unknown> }>(
      "SELECT encrypted_secret,config FROM integration_configs WHERE provider=$1 LIMIT 1 FOR UPDATE",
      [GSC_PROVIDER],
    );
    const current = existing.rows[0];
    const secret = input.clientSecret?.trim();
    const previousClientId = typeof current?.config?.clientId === "string" ? current.config.clientId.trim() : "";
    const clientIdChanged = Boolean(previousClientId && previousClientId !== clientId);

    if (clientIdChanged && !secret) {
      throw new Error("با تغییر Google Client ID باید Client Secret مربوط به همان OAuth Client را نیز وارد کنید.");
    }

    const encryptedSecret = secret ? encryptSecret(secret) : current?.encrypted_secret ?? null;
    if (!encryptedSecret) throw new Error("Google Client Secret الزامی است.");

    const credentialsChanged = Boolean(secret) || previousClientId !== clientId;

    await client.query(
      `INSERT INTO integration_configs (provider,config,encrypted_secret,updated_at)
       VALUES ($1,$2,$3,NOW())
       ON CONFLICT (provider) DO UPDATE SET config=EXCLUDED.config,encrypted_secret=EXCLUDED.encrypted_secret,updated_at=NOW()`,
      [GSC_PROVIDER, JSON.stringify({ clientId }), encryptedSecret],
    );

    if (credentialsChanged) {
      await client.query("UPDATE wordpress_sites SET gsc_property_url=NULL,updated_at=NOW()");
      await client.query("DELETE FROM gsc_connection WHERE id=1");
    }

    await client.query(
      "INSERT INTO audit_logs (action,details) VALUES ('gsc.oauth_config_updated',$1)",
      [JSON.stringify({ clientIdChanged: previousClientId !== clientId, secretChanged: Boolean(secret), connectionReset: credentialsChanged })],
    );
    await client.query("COMMIT");
    return { credentialsChanged };
  } catch (error) {
    await client.query("ROLLBACK").catch(() => undefined);
    throw error;
  } finally {
    client.release();
  }
}

export async function clearGscOAuthCredentials() {
  await initializeDatabase();
  const client = await db.connect();
  try {
    await client.query("BEGIN");
    await client.query("UPDATE wordpress_sites SET gsc_property_url=NULL,updated_at=NOW()");
    await client.query("DELETE FROM gsc_connection WHERE id=1");
    await client.query("DELETE FROM integration_configs WHERE provider=$1", [GSC_PROVIDER]);
    await client.query("INSERT INTO audit_logs (action) VALUES ('gsc.oauth_config_removed')");
    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK").catch(() => undefined);
    throw error;
  } finally {
    client.release();
  }
}
