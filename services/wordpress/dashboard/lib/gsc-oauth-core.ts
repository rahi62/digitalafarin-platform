const GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";

export type GscAuthErrorCode = "gsc_reauthorization_required" | "gsc_refresh_failed";

export class GscAuthError extends Error {
  constructor(
    readonly code: GscAuthErrorCode,
    message: string,
    readonly status: number,
    readonly googleStatus?: number,
  ) {
    super(message);
    this.name = "GscAuthError";
  }
}

export function buildGscAuthorizationUrl(input: {
  clientId: string;
  redirectUri: string;
  state: string;
  scope: string;
}) {
  const url = new URL(GOOGLE_AUTH_URL);
  url.searchParams.set("client_id", input.clientId);
  url.searchParams.set("redirect_uri", input.redirectUri);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", input.scope);
  url.searchParams.set("access_type", "offline");
  url.searchParams.set("prompt", "consent");
  url.searchParams.set("include_granted_scopes", "true");
  url.searchParams.set("state", input.state);
  return url.toString();
}

export function selectPersistedRefreshToken(received?: string, previous?: string) {
  const selected = received?.trim() || previous?.trim();
  if (!selected) {
    throw new GscAuthError(
      "gsc_reauthorization_required",
      "Google did not return offline authorization. Reconnect Search Console.",
      401,
    );
  }
  return selected;
}

export async function persistRefreshToken(
  received: string | undefined,
  previous: string | undefined,
  persist: (refreshToken: string) => Promise<void>,
) {
  const refreshToken = selectPersistedRefreshToken(received, previous);
  await persist(refreshToken);
  return refreshToken;
}

export async function exchangeRefreshToken(
  refreshToken: string,
  exchange: (refreshToken: string) => Promise<{ access_token?: string; expires_in?: number }>,
) {
  const token = await exchange(refreshToken);
  if (!token.access_token) {
    throw new GscAuthError("gsc_refresh_failed", "Google did not return an access token.", 502);
  }
  return token.access_token;
}

export async function resolveGscAccessToken(
  loadCredential: () => Promise<{
    refreshToken: string;
    accessToken?: string;
    accessTokenExpiresAt?: Date;
    version?: string;
  }>,
  exchange: (refreshToken: string) => Promise<{ access_token?: string; expires_in?: number }>,
  persistAccessToken: (value: { accessToken: string; expiresAt: Date; version?: string }) => Promise<boolean | void>,
  now = new Date(),
) {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const credential = await loadCredential();
    if (credential.accessToken && credential.accessTokenExpiresAt
      && credential.accessTokenExpiresAt.getTime() > now.getTime() + 60_000) {
      return credential.accessToken;
    }
    const token = await exchange(credential.refreshToken);
    if (!token.access_token) {
      throw new GscAuthError("gsc_refresh_failed", "Google did not return an access token.", 502);
    }
    const expiresAt = new Date(now.getTime() + (token.expires_in ?? 3600) * 1000);
    const persisted = await persistAccessToken({ accessToken: token.access_token, expiresAt, version: credential.version });
    if (persisted !== false) return token.access_token;
  }
  throw new GscAuthError("gsc_refresh_failed", "Google credential changed repeatedly during refresh.", 502);
}
