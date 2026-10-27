import { NextResponse } from "next/server";
import { gscCallbackUrl, resolvePublicOrigin } from "@/lib/public-origin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { isAuthenticated } = await import("@/lib/session");
  if (!(await isAuthenticated())) return NextResponse.redirect(new URL("/login", request.url));
  try {
    const origin = resolvePublicOrigin(request.headers, request.url);
    const callback = gscCallbackUrl(origin);
    const { createGscOAuthUrl } = await import("@/lib/gsc");
    return NextResponse.redirect(await createGscOAuthUrl(callback));
  } catch (error) {
    const message = error instanceof Error ? error.message : "شروع اتصال Google Search Console ناموفق بود.";
    return NextResponse.redirect(new URL(`/settings?gscError=${encodeURIComponent(message)}`, request.url));
  }
}
