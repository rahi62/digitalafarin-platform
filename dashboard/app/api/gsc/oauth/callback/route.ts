import { NextRequest, NextResponse } from "next/server";
import { completeGscOAuth } from "@/lib/gsc";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const error = request.nextUrl.searchParams.get("error");
  if (error) {
    return NextResponse.redirect(new URL(`/settings?gscError=${encodeURIComponent(error)}`, request.url));
  }
  const code = request.nextUrl.searchParams.get("code")?.trim();
  const state = request.nextUrl.searchParams.get("state")?.trim();
  if (!code || !state) {
    return NextResponse.redirect(new URL("/settings?gscError=Missing%20OAuth%20code%20or%20state", request.url));
  }
  try {
    const properties = await completeGscOAuth(code, state);
    return NextResponse.redirect(new URL(`/settings?gscConnected=1&properties=${properties.length}`, request.url));
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : "تکمیل اتصال Google Search Console ناموفق بود.";
    return NextResponse.redirect(new URL(`/settings?gscError=${encodeURIComponent(message)}`, request.url));
  }
}
