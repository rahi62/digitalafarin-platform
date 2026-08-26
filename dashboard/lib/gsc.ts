import { createHash, randomBytes } from "node:crypto";
import { decryptSecret, encryptSecret } from "./crypto";
import { db, initializeDatabase } from "./db";
import { getGscOAuthCredentials } from "./integration-settings";

const GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly";
const GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";
const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";
const GSC_API_ROOT = "https://www.googleapis.com/webmasters/v3";

export type GscProperty = {
  siteUrl: string;
  permissionLevel: string;
};

function hashState(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function normalizeRedirectUri(value: string) {
  const url = new URL(value);
  const localHttp = url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname);
  if (url.protocol !== "https:" && !localHttp) {
    throw new Error("OAuth callback باید HTTPS باشد؛ فقط localhost در توسعه می‌تواند HTTP باشد.");
  }
  if (url.username || url.password) throw new Error("OAuth callback معتبر نیست.");
  return url.toString();
}

async function googleJson<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store", signal: AbortSignal.timeout(20_000) });
  const data = await response.json().catch(() => null) as (T & { error?: string; error_description?: string; message?: string }) | null;
  if (!response.ok || data === null) {
    throw new Error(data?.error_description || data?.message || data?.error || `Google API returned HTTP ${response.status}`);
  }
  return data;
}

export async function createGscOAuthUrl(redirectUri: string) {
  const config = await getGscOAuthCredentials();
  const callback = normalizeRedirectUri(redirectUri);
  await initializeDatabase();
  const state = randomBytes(32).toString("base64url");
  await db.query(
    "INSERT INTO gsc_oauth_states (state_hash,redirect_uri,expires_at) VALUES ($1,$2,NOW() + INTERVAL '10 minutes')",
    [hashState(state), callback],
  );

  const url = new URL(GOOGLE_AUTH_URL);
  url.searchParams.set("client_id", config.clientId);
  url.searchParams.set("redirect_uri", callback);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", GSC_SCOPE);
  url.searchParams.set("access_type", "offline");
  url.searchParams.set("prompt", "consent");
  url.searchParams.set("include_granted_scopes", "true");
  url.searchParams.set("state", state);
  return url.toString();
}

async function consumeOAuthState(state: string) {
  await initializeDatabase();
  const result = await db.query<{ redirect_uri: string | null }>(
    "DELETE FROM gsc_oauth_states WHERE state_hash=$1 AND expires_at >= NOW() RETURNING redirect_uri",
    [hashState(state)],
  );
  const row = result.rows[0];
  if (!row) throw new Error("OAuth state نامعتبر یا منقضی شده است. اتصال را دوباره شروع کنید.");
  if (!row.redirect_uri) throw new Error("OAuth callback برای این درخواست ثبت نشده است. اتصال را دوباره شروع کنید.");
  return normalizeRedirectUri(row.redirect_uri);
}

export async function completeGscOAuth(code: string, state: string) {
  const config = await getGscOAuthCredentials();
  const redirectUri = await consumeOAuthState(state);
  const body = new URLSearchParams({
    client_id: config.clientId,
    client_secret: config.clientSecret,
    redirect_uri: redirectUri,
    grant_type: "authorization_code",
    code,
  });
  const token = await googleJson<{ access_token: string; refresh_token?: string; scope?: string; expires_in?: number }>(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!token.refresh_token) throw new Error("Google refresh token برنگرداند. اتصال را با دسترسی مجدد انجام دهید.");

  const properties = await listGscPropertiesWithToken(token.access_token);
  await initializeDatabase();
  await db.query(
    `INSERT INTO gsc_connection (id,encrypted_refresh_token,scope,last_check_status,last_check_message,last_checked_at,connected_at,updated_at)
     VALUES (1,$1,$2,'ok',$3,NOW(),NOW(),NOW())
     ON CONFLICT (id) DO UPDATE SET encrypted_refresh_token=EXCLUDED.encrypted_refresh_token,scope=EXCLUDED.scope,
       last_check_status='ok',last_check_message=EXCLUDED.last_check_message,last_checked_at=NOW(),connected_at=NOW(),updated_at=NOW()`,
    [encryptSecret(token.refresh_token), token.scope ?? GSC_SCOPE, `${properties.length} Search Console properties available`],
  );
  await db.query("INSERT INTO audit_logs (action,details) VALUES ('gsc.connected',$1)", [JSON.stringify({ properties: properties.length })]);
  return properties;
}

export async function getGscAccessToken() {
  const config = await getGscOAuthCredentials();
  await initializeDatabase();
  const result = await db.query<{ encrypted_refresh_token: string }>("SELECT encrypted_refresh_token FROM gsc_connection WHERE id=1 LIMIT 1");
  const row = result.rows[0];
  if (!row) throw new Error("Google Search Console هنوز به پنل متصل نشده است.");
  const body = new URLSearchParams({
    client_id: config.clientId,
    client_secret: config.clientSecret,
    refresh_token: decryptSecret(row.encrypted_refresh_token),
    grant_type: "refresh_token",
  });
  const token = await googleJson<{ access_token: string; expires_in?: number }>(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  return token.access_token;
}

export async function listGscPropertiesWithToken(accessToken: string): Promise<GscProperty[]> {
  const data = await googleJson<{ siteEntry?: Array<{ siteUrl?: string; permissionLevel?: string }> }>(`${GSC_API_ROOT}/sites`, {
    headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" },
  });
  return (data.siteEntry ?? [])
    .filter((item): item is { siteUrl: string; permissionLevel?: string } => Boolean(item.siteUrl))
    .map((item) => ({ siteUrl: item.siteUrl, permissionLevel: item.permissionLevel ?? "unknown" }))
    .sort((a, b) => a.siteUrl.localeCompare(b.siteUrl));
}

export async function listGscProperties() {
  return listGscPropertiesWithToken(await getGscAccessToken());
}

export async function testGscConnection() {
  try {
    const properties = await listGscProperties();
    await initializeDatabase();
    await db.query("UPDATE gsc_connection SET last_check_status='ok',last_check_message=$1,last_checked_at=NOW(),updated_at=NOW() WHERE id=1", [`${properties.length} Search Console properties available`]);
    await db.query("INSERT INTO audit_logs (action,details) VALUES ('gsc.health_checked',$1)", [JSON.stringify({ status: "ok", properties: properties.length })]);
    return properties;
  } catch (error) {
    const message = error instanceof Error ? error.message.slice(0, 500) : "GSC connection failed";
    await initializeDatabase();
    await db.query("UPDATE gsc_connection SET last_check_status='error',last_check_message=$1,last_checked_at=NOW(),updated_at=NOW() WHERE id=1", [message]);
    await db.query("INSERT INTO audit_logs (action,details) VALUES ('gsc.health_checked',$1)", [JSON.stringify({ status: "error", message })]);
    throw error;
  }
}

export async function disconnectGsc() {
  await initializeDatabase();
  await db.query("UPDATE wordpress_sites SET gsc_property_url=NULL,updated_at=NOW()");
  await db.query("DELETE FROM gsc_connection WHERE id=1");
  await db.query("INSERT INTO audit_logs (action) VALUES ('gsc.disconnected')");
}
