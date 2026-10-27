import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { dashboardConfig } from "./config";

const COOKIE = "wp_agent_session";
const payload = "digitalafarin-admin-v1";

function signature() {
  return createHmac("sha256", dashboardConfig.sessionSecret).update(payload).digest("base64url");
}

export async function isAuthenticated() {
  const value = (await cookies()).get(COOKIE)?.value ?? "";
  const expected = signature();
  const a = Buffer.from(value);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function requireAdmin() {
  if (!(await isAuthenticated())) redirect("/login");
}

export async function createSession() {
  (await cookies()).set(COOKIE, signature(), { httpOnly: true, secure: true, sameSite: "strict", path: "/", maxAge: 60 * 60 * 12 });
}

export async function clearSession() {
  (await cookies()).delete(COOKIE);
}
