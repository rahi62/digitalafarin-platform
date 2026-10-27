import { Router } from "express";
import { eq } from "drizzle-orm";
import { z } from "zod";
import { recordActivity } from "../activity/service.js";
import { createCsrfToken, requireCsrf } from "../auth/csrf.js";
import { authenticateRequest, type AuthenticatedRequest } from "../auth/middleware.js";
import { getUserPermissions } from "../auth/permissions.js";
import { verifyPassword } from "../auth/password.js";
import { createSession, revokeSession } from "../auth/session.js";
import { config } from "../config.js";
import { getDb } from "../db/client.js";
import { users } from "../db/schema.js";
import { createRateLimit } from "./rate-limit.js";
import { fail, internalError, ok } from "./response.js";

const loginSchema = z.object({
  email: z.string().email().max(320).transform((value) => value.trim().toLowerCase()),
  password: z.string().min(1).max(1000),
});

const loginLimiter = createRateLimit({ windowMs: 15 * 60 * 1000, max: 10, keyPrefix: "agency-login" });

function cookieOptions(expires?: Date) {
  return {
    httpOnly: true,
    secure: config.adminOrigin.startsWith("https://"),
    sameSite: "lax" as const,
    path: "/",
    ...(expires ? { expires } : {}),
  };
}

function sameAdminOrigin(origin: string | undefined): boolean {
  return origin === config.adminOrigin;
}

export function createAuthRouter() {
  const router = Router();

  router.post("/login", loginLimiter, async (request, response) => {
    try {
      if (!sameAdminOrigin(request.headers.origin)) return fail(response, 403, "INVALID_ORIGIN", "Request origin is not allowed");
      const parsed = loginSchema.safeParse(request.body);
      if (!parsed.success) return fail(response, 400, "INVALID_INPUT", "Invalid login request");

      const db = getDb();
      const [user] = await db.select().from(users).where(eq(users.email, parsed.data.email)).limit(1);
      const valid = user && user.status === "active" && (await verifyPassword(user.passwordHash, parsed.data.password));
      if (!valid || !user) return fail(response, 401, "INVALID_CREDENTIALS", "Email or password is incorrect");

      const session = await createSession(user.id, { ip: request.ip, userAgent: request.headers["user-agent"] });
      response.cookie(config.sessionCookieName, session.token, cookieOptions(session.expiresAt));

      await recordActivity({
        actorType: "user",
        actorId: user.id,
        actorLabel: user.displayName,
        entityType: "auth",
        entityId: user.id,
        action: "auth.login",
        summary: "User logged in to Agency Control Center",
      });

      return ok(response, {
        user: { id: user.id, email: user.email, displayName: user.displayName },
        csrfToken: createCsrfToken(session.token),
        expiresAt: session.expiresAt.toISOString(),
      });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.get("/me", authenticateRequest, async (request, response) => {
    try {
      const req = request as AuthenticatedRequest;
      if (!req.auth) return fail(response, 401, "AUTH_REQUIRED", "Authentication required");
      const permissions = [...(await getUserPermissions(req.auth.userId))];
      return ok(response, { user: req.auth, permissions });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.get("/csrf", authenticateRequest, (request, response) => {
    try {
      const req = request as AuthenticatedRequest;
      if (!req.sessionToken) return fail(response, 401, "AUTH_REQUIRED", "Authentication required");
      return ok(response, { csrfToken: createCsrfToken(req.sessionToken) });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.post("/logout", authenticateRequest, requireCsrf, async (request, response) => {
    try {
      const req = request as AuthenticatedRequest;
      if (req.sessionToken) await revokeSession(req.sessionToken);
      response.clearCookie(config.sessionCookieName, cookieOptions());
      if (req.auth) {
        await recordActivity({
          actorType: "user",
          actorId: req.auth.userId,
          actorLabel: req.auth.displayName,
          entityType: "auth",
          entityId: req.auth.userId,
          action: "auth.logout",
          summary: "User logged out of Agency Control Center",
        });
      }
      return ok(response, { loggedOut: true });
    } catch (error) {
      return internalError(response, error);
    }
  });

  return router;
}
