import type { NextFunction, Request, RequestHandler, Response } from "express";
import { config } from "../config.js";
import { userHasPermission, type PermissionKey } from "./permissions.js";
import { resolveSession, type SessionContext } from "./session.js";

export type AuthenticatedRequest = Request & {
  auth?: SessionContext;
  sessionToken?: string;
};

export function parseCookieHeader(header: string | undefined): Record<string, string> {
  if (!header) return {};
  const result: Record<string, string> = {};
  for (const part of header.split(";")) {
    const index = part.indexOf("=");
    if (index < 1) continue;
    const key = part.slice(0, index).trim();
    const value = part.slice(index + 1).trim();
    if (!key) continue;
    try {
      result[key] = decodeURIComponent(value);
    } catch {
      result[key] = value;
    }
  }
  return result;
}

export const authenticateRequest: RequestHandler = async (request, response, next) => {
  const req = request as AuthenticatedRequest;
  const cookies = parseCookieHeader(req.headers.cookie);
  const token = cookies[config.sessionCookieName];
  if (!token) {
    response.status(401).json({ data: null, error: { code: "AUTH_REQUIRED", message: "Authentication required" } });
    return;
  }

  const session = await resolveSession(token);
  if (!session) {
    response.status(401).json({ data: null, error: { code: "INVALID_SESSION", message: "Session is invalid or expired" } });
    return;
  }

  req.auth = session;
  req.sessionToken = token;
  next();
};

export function requirePermission(permission: PermissionKey): RequestHandler {
  return async (request: Request, response: Response, next: NextFunction) => {
    const req = request as AuthenticatedRequest;
    if (!req.auth) {
      response.status(401).json({ data: null, error: { code: "AUTH_REQUIRED", message: "Authentication required" } });
      return;
    }

    if (!(await userHasPermission(req.auth.userId, permission))) {
      response.status(403).json({ data: null, error: { code: "FORBIDDEN", message: "Permission denied" } });
      return;
    }

    next();
  };
}
