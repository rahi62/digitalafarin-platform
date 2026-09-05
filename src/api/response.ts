import type { Response } from "express";

export function ok<T>(response: Response, data: T, status = 200) {
  return response.status(status).json({ data, error: null });
}

export function fail(response: Response, status: number, code: string, message: string) {
  return response.status(status).json({ data: null, error: { code, message } });
}

export function internalError(response: Response, error: unknown) {
  const requestId = crypto.randomUUID();
  console.error(JSON.stringify({
    event: "api_request_failed",
    requestId,
    error: error instanceof Error ? error.message : "unknown",
  }));
  return response.status(500).json({
    data: null,
    error: { code: "INTERNAL_ERROR", message: "Internal server error", requestId },
  });
}
