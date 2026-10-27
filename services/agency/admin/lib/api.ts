"use client";

import type { ApiEnvelope } from "./types";

export class AgencyApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "AgencyApiError";
  }
}

async function unwrap<T>(response: Response): Promise<T> {
  let payload: ApiEnvelope<T> | null = null;
  try {
    payload = (await response.json()) as ApiEnvelope<T>;
  } catch {
    throw new AgencyApiError(response.status, "INVALID_RESPONSE", "پاسخ سرور قابل خواندن نیست.");
  }

  if (!response.ok || payload.error || payload.data === null) {
    throw new AgencyApiError(
      response.status,
      payload.error?.code ?? "REQUEST_FAILED",
      payload.error?.message ?? "درخواست با خطا مواجه شد.",
    );
  }

  return payload.data;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  return unwrap<T>(response);
}

async function getCsrfToken(): Promise<string> {
  const result = await apiGet<{ csrfToken: string }>("/api/v1/auth/csrf");
  return result.csrfToken;
}

export async function apiMutation<T>(
  path: string,
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  body?: unknown,
): Promise<T> {
  const csrfToken = await getCsrfToken();
  const response = await fetch(path, {
    method,
    credentials: "include",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken,
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return unwrap<T>(response);
}

export async function login(email: string, password: string) {
  const response = await fetch("/api/v1/auth/login", {
    method: "POST",
    credentials: "include",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, password }),
  });
  return unwrap<{ user: { id: string; email: string; displayName: string }; csrfToken: string; expiresAt: string }>(response);
}

export async function logout() {
  return apiMutation<{ loggedOut: boolean }>("/api/v1/auth/logout", "POST", {});
}
