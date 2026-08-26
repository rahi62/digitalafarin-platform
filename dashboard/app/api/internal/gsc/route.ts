import { NextRequest, NextResponse } from "next/server";
import { db, initializeDatabase } from "@/lib/db";
import { getGscAccessToken } from "@/lib/gsc";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function internalOnly(request: NextRequest) {
  const host = request.headers.get("host") ?? "";
  const loopbackHost = host === "127.0.0.1" || host.startsWith("127.0.0.1:") || host === "localhost" || host.startsWith("localhost:");
  return request.headers.get("x-digitalafarin-internal-mcp") === "1" && loopbackHost;
}

export async function GET(request: NextRequest) {
  if (!internalOnly(request)) return NextResponse.json({ error: "Not found" }, { status: 404 });
  await initializeDatabase();
  const siteId = request.nextUrl.searchParams.get("siteId")?.trim();
  const operation = request.nextUrl.searchParams.get("operation")?.trim().slice(0, 100) || "unknown";

  if (!siteId) {
    const result = await db.query<{ id: string; name: string; base_url: string; gsc_property_url: string }>(
      `SELECT id,name,base_url,gsc_property_url FROM wordpress_sites
       WHERE enabled=TRUE AND gsc_property_url IS NOT NULL AND gsc_property_url <> '' ORDER BY name ASC`,
    );
    return NextResponse.json({ sites: result.rows.map((site) => ({ id: site.id, name: site.name, baseUrl: site.base_url, propertyUrl: site.gsc_property_url })) });
  }

  const result = await db.query<{ id: string; name: string; base_url: string; gsc_property_url: string }>(
    `SELECT id,name,base_url,gsc_property_url FROM wordpress_sites
     WHERE id=$1 AND enabled=TRUE AND gsc_property_url IS NOT NULL AND gsc_property_url <> '' LIMIT 1`,
    [siteId],
  );
  const site = result.rows[0];
  if (!site) return NextResponse.json({ error: "GSC property is not mapped for this enabled site" }, { status: 404 });

  try {
    const accessToken = await getGscAccessToken();
    await db.query("INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'agent.gsc_resolved',$2)", [site.id, JSON.stringify({ operation, propertyUrl: site.gsc_property_url })]);
    return NextResponse.json({
      site: { id: site.id, name: site.name, baseUrl: site.base_url, propertyUrl: site.gsc_property_url },
      accessToken,
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "Unable to resolve GSC access" }, { status: 502 });
  }
}
