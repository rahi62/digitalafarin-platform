import { NextRequest, NextResponse } from "next/server";
import { completeGscOAuth } from "@/lib/gsc";
import { resolvePublicOrigin } from "@/lib/public-origin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function settingsUrl(request: NextRequest, params: Record<string, string>) {
  const origin = resolvePublicOrigin(request.headers, request.url);
  const url = new URL("/settings", `${origin}/`);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return url;
}

export async function GET(request: NextRequest) {
  const error = request.nextUrl.searchParams.get("error");
  if (error) {
    return NextResponse.redirect(settingsUrl(request, { gscError: error }));
  }

  const code = request.nextUrl.searchParams.get("code")?.trim();
  const state = request.nextUrl.searchParams.get("state")?.trim();
  if (!code || !state) {
    return NextResponse.redirect(settingsUrl(request, { gscError: "Missing OAuth code or state" }));
  }

  try {
    const properties = await completeGscOAuth(code, state);
    return NextResponse.redirect(settingsUrl(request, {
      gscConnected: "1",
      properties: String(properties.length),
    }));
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : "تکمیل اتصال Google Search Console ناموفق بود.";
    return NextResponse.redirect(settingsUrl(request, { gscError: message }));
  }
}
