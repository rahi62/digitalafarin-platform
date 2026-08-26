import { NextRequest, NextResponse } from "next/server";
import { decryptSecret } from "@/lib/crypto";
import { db, initializeDatabase } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function internalOnly(request: NextRequest) {
  const host = request.headers.get("host") ?? "";
  const loopbackHost =
    host === "127.0.0.1" ||
    host.startsWith("127.0.0.1:") ||
    host === "localhost" ||
    host.startsWith("localhost:");

  return (
    request.headers.get("x-digitalafarin-internal-mcp") === "1" &&
    loopbackHost
  );
}

export async function GET(request: NextRequest) {
  if (!internalOnly(request)) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  await initializeDatabase();
  const siteId = request.nextUrl.searchParams.get("siteId")?.trim();
  const operation = request.nextUrl.searchParams.get("operation")?.trim().slice(0, 100) || "unknown";

  if (!siteId) {
    const result = await db.query<{
      id: string;
      name: string;
      base_url: string;
      username: string;
      last_check_status: string | null;
      last_checked_at: Date | null;
    }>(
      `SELECT id,name,base_url,username,last_check_status,last_checked_at
       FROM wordpress_sites
       WHERE enabled=TRUE
       ORDER BY name ASC`,
    );

    return NextResponse.json({
      sites: result.rows.map((site) => ({
        id: site.id,
        name: site.name,
        baseUrl: site.base_url,
        username: site.username,
        lastCheckStatus: site.last_check_status,
        lastCheckedAt: site.last_checked_at,
      })),
    });
  }

  const result = await db.query<{
    id: string;
    name: string;
    base_url: string;
    username: string;
    encrypted_app_password: string;
  }>(
    `SELECT id,name,base_url,username,encrypted_app_password
     FROM wordpress_sites
     WHERE id=$1 AND enabled=TRUE
     LIMIT 1`,
    [siteId],
  );

  const site = result.rows[0];
  if (!site) {
    return NextResponse.json({ error: "Site not found or disabled" }, { status: 404 });
  }

  await db.query(
    "INSERT INTO audit_logs (site_id,action,details) VALUES ($1,'agent.site_resolved',$2)",
    [site.id, JSON.stringify({ operation })],
  );

  return NextResponse.json({
    site: {
      id: site.id,
      name: site.name,
      baseUrl: site.base_url,
      username: site.username,
      appPassword: decryptSecret(site.encrypted_app_password),
    },
  });
}
