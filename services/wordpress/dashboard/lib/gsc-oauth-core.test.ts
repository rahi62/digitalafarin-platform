import assert from "node:assert/strict";
import test from "node:test";
import {
  buildGscAuthorizationUrl,
  exchangeRefreshToken,
  GscAuthError,
  persistRefreshToken,
  resolveGscAccessToken,
  selectPersistedRefreshToken,
} from "./gsc-oauth-core";

test("OAuth authorization requests offline access and explicit consent", () => {
  const url = new URL(buildGscAuthorizationUrl({
    clientId: "client-id",
    redirectUri: "https://wp-agent.example/api/gsc/oauth/callback",
    state: "state-value",
    scope: "scope-value",
  }));

  assert.equal(url.searchParams.get("access_type"), "offline");
  assert.equal(url.searchParams.get("prompt"), "consent");
});

test("expired access token with a valid refresh token obtains a fresh access token", async () => {
  let exchanges = 0;
  let persisted: { accessToken: string; expiresAt: Date } | undefined;
  const accessToken = await resolveGscAccessToken(
    async () => ({ refreshToken: "stored-refresh-token", accessToken: "expired-access-token", accessTokenExpiresAt: new Date("2026-09-09T09:00:00Z") }),
    async () => {
    exchanges += 1;
    return { access_token: "fresh-access-token", expires_in: 3600 };
    },
    async (value) => { persisted = value; },
    new Date("2026-09-09T10:00:00Z"),
  );

  assert.equal(accessToken, "fresh-access-token");
  assert.equal(exchanges, 1);
  assert.equal(persisted?.accessToken, "fresh-access-token");
  assert.equal(persisted?.expiresAt.toISOString(), "2026-09-09T11:00:00.000Z");
});

test("a valid persisted access token is used without refreshing", async () => {
  let exchanges = 0;
  const accessToken = await resolveGscAccessToken(
    async () => ({ refreshToken: "stored-refresh-token", accessToken: "valid-access-token", accessTokenExpiresAt: new Date("2026-09-09T11:00:00Z") }),
    async () => { exchanges += 1; return { access_token: "unexpected" }; },
    async () => undefined,
    new Date("2026-09-09T10:00:00Z"),
  );

  assert.equal(accessToken, "valid-access-token");
  assert.equal(exchanges, 0);
});

test("expired access token with a revoked refresh token returns reauthorization_required", async () => {
  await assert.rejects(
    () => exchangeRefreshToken("revoked-refresh-token", async () => {
      throw new GscAuthError("gsc_reauthorization_required", "Google authorization is no longer valid.", 401, 400);
    }),
    (error: unknown) => error instanceof GscAuthError
      && error.code === "gsc_reauthorization_required"
      && error.status === 401,
  );
});

test("OAuth reconnect persists a newly returned refresh token", async () => {
  let persisted = "";
  await persistRefreshToken("new-refresh-token", "old-refresh-token", async (token) => { persisted = token; });
  assert.equal(persisted, "new-refresh-token");
});

test("OAuth reconnect without a refresh token preserves the prior valid token", () => {
  assert.equal(selectPersistedRefreshToken(undefined, "old-refresh-token"), "old-refresh-token");
});

test("OAuth connection without any refresh token requires reauthorization", () => {
  assert.throws(
    () => selectPersistedRefreshToken(undefined, undefined),
    (error: unknown) => error instanceof GscAuthError && error.code === "gsc_reauthorization_required",
  );
});

test("each operation reloads the current persisted credential without a service restart", async () => {
  const stored = ["first-refresh-token", "updated-refresh-token"];
  const seen: string[] = [];
  const load = async () => ({ refreshToken: stored.shift() as string });
  const exchange = async (refreshToken: string) => {
    seen.push(refreshToken);
    return { access_token: `access-for-${refreshToken}` };
  };

  await resolveGscAccessToken(load, exchange, async () => undefined);
  await resolveGscAccessToken(load, exchange, async () => undefined);

  assert.deepEqual(seen, ["first-refresh-token", "updated-refresh-token"]);
});

test("an in-flight refresh cannot overwrite a concurrently reconnected credential", async () => {
  let loads = 0;
  const seen: string[] = [];
  const accessToken = await resolveGscAccessToken(
    async () => {
      loads += 1;
      return loads === 1
        ? { refreshToken: "old-refresh-token", version: "old-version" }
        : { refreshToken: "new-refresh-token", accessToken: "new-account-access", accessTokenExpiresAt: new Date("2026-09-09T11:00:00Z"), version: "new-version" };
    },
    async (refreshToken) => {
      seen.push(refreshToken);
      return { access_token: "old-account-access", expires_in: 3600 };
    },
    async () => false,
    new Date("2026-09-09T10:00:00Z"),
  );

  assert.equal(accessToken, "new-account-access");
  assert.deepEqual(seen, ["old-refresh-token"]);
  assert.equal(loads, 2);
});
