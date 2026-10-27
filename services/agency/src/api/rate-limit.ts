import type { RequestHandler } from "express";

export function createRateLimit(options: { windowMs: number; max: number; keyPrefix: string }): RequestHandler {
  const buckets = new Map<string, { count: number; resetAt: number }>();

  return (request, response, next) => {
    const now = Date.now();
    const remote = request.ip || request.socket.remoteAddress || "unknown";
    const key = `${options.keyPrefix}:${remote}`;
    const current = buckets.get(key);

    if (!current || current.resetAt <= now) {
      buckets.set(key, { count: 1, resetAt: now + options.windowMs });
      next();
      return;
    }

    current.count += 1;
    if (current.count > options.max) {
      response.setHeader("Retry-After", Math.max(1, Math.ceil((current.resetAt - now) / 1000)));
      response.status(429).json({ data: null, error: { code: "RATE_LIMITED", message: "Too many requests" } });
      return;
    }

    next();
  };
}
