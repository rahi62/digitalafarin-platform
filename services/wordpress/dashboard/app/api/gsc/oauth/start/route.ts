import { NextResponse } from "next/server";
import { createGscOAuthUrl } from "@/lib/gsc";
import { gscCallbackUrl, resolvePublicOrigin } from "@/lib/public-origin";
import { isAuthenticated } from "@/lib/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (!(await isAuthenticated())) return NextResponse.redirect(new URL("/login", request.url));
  try {
    const origin = resolvePublicOrigin(request.headers, request.url);
    const callback = gscCallbackUrl(origin);
    return NextResponse.redirect(await createGscOAuthUrl(callback));
  } catch (error) {
    const message = error instanceof Error ? error.message : "شروع اتصال Google Search Console ناموفق بود.";
    return NextResponse.redirect(new URL(`/settings?gscError=${encodeURIComponent(message)}`, request.url));
  }
}
