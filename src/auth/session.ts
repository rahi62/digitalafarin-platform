import { createHash, randomBytes } from "node:crypto";
import { and, eq, gt } from "drizzle-orm";
import { config } from "../config.js";
import { getDb } from "../db/client.js";
import { sessions, users } from "../db/schema.js";

export type SessionContext = {
  sessionId: string;
  userId: string;
  email: string;
  displayName: string;
  expiresAt: Date;
};

export type CreatedSession = {
  token: string;
  expiresAt: Date;
};

export function hashOpaqueToken(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

export function hashIp(value: string | undefined): string | undefined {
  return value ? hashOpaqueToken(value) : undefined;
}

export async function createSession(
  userId: string,
  metadata: { ip?: string; userAgent?: string } = {},
): Promise<CreatedSession> {
  const db = getDb();
  const [user] = await db
    .select({ id: users.id, status: users.status })
    .from(users)
    .where(eq(users.id, userId))
    .limit(1);

  if (!user || user.status !== "active") throw new Error("User is not active");

  const token = randomBytes(32).toString("base64url");
  const expiresAt = new Date(Date.now() + config.sessionTtlHours * 60 * 60 * 1000);

  await db.insert(sessions).values({
    userId,
    tokenHash: hashOpaqueToken(token),
    expiresAt,
    ipHash: hashIp(metadata.ip),
    userAgent: metadata.userAgent?.slice(0, 1000),
  });

  return { token, expiresAt };
}

export async function resolveSession(token: string): Promise<SessionContext | null> {
  if (!token) return null;
  const db = getDb();
  const now = new Date();
  const tokenHash = hashOpaqueToken(token);

  const [row] = await db
    .select({
      sessionId: sessions.id,
      userId: users.id,
      email: users.email,
      displayName: users.displayName,
      expiresAt: sessions.expiresAt,
    })
    .from(sessions)
    .innerJoin(users, eq(sessions.userId, users.id))
    .where(and(eq(sessions.tokenHash, tokenHash), gt(sessions.expiresAt, now), eq(users.status, "active")))
    .limit(1);

  if (!row) return null;

  await db.update(sessions).set({ lastSeenAt: now }).where(eq(sessions.id, row.sessionId));
  return row;
}

export async function revokeSession(token: string): Promise<void> {
  if (!token) return;
  const db = getDb();
  await db.delete(sessions).where(eq(sessions.tokenHash, hashOpaqueToken(token)));
}

export async function revokeSessionById(sessionId: string): Promise<void> {
  const db = getDb();
  await db.delete(sessions).where(eq(sessions.id, sessionId));
}
