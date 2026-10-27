import { createHmac, timingSafeEqual } from "node:crypto";
import type { RequestHandler } from "express";
import { config } from "../config.js";
import type { AuthenticatedRequest } from "./middleware.js";

function csrfSecret(): string {
  if (!config.csrfSecret || config.csrfSecret.length < 32) {
    throw new Error("CSRF_SECRET must be configured with at least 32 characters");
  }
  return config.csrfSecret;
}

export function createCsrfToken(sessionToken: string): string {
  return createHmac("sha256", csrfSecret()).update(`digitalafarin-agency-csrf:${sessionToken}`).digest("base64url");
}

export function verifyCsrfToken(sessionToken: string, candidate: string): boolean {
  const expected = createCsrfToken(sessionToken);
  const expectedBuffer = Buffer.from(expected);
  const candidateBuffer = Buffer.from(candidate);
  return expectedBuffer.length === candidateBuffer.length && timingSafeEqual(expectedBuffer, candidateBuffer);
}

const safeMethods = new Set(["GET", "HEAD", "OPTIONS"]);

export const requireCsrf: RequestHandler = (request, response, next) => {
  if (safeMethods.has(request.method.toUpperCase())) {
    next();
    return;
  }

  const req = request as AuthenticatedRequest;
  const origin = request.headers.origin;
  if (origin !== config.adminOrigin) {
    response.status(403).json({ data: null, error: { code: "INVALID_ORIGIN", message: "Request origin is not allowed" } });
    return;
  }

  const token = request.headers["x-csrf-token"];
  if (!req.sessionToken || typeof token !== "string" || !verifyCsrfToken(req.sessionToken, token)) {
    response.status(403).json({ data: null, error: { code: "INVALID_CSRF", message: "CSRF validation failed" } });
    return;
  }

  next();
};
