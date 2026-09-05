import { Router } from "express";
import { eq } from "drizzle-orm";
import { z } from "zod";
import { recordActivity } from "../activity/service.js";
import { requirePermission, type AuthenticatedRequest } from "../auth/middleware.js";
import { getDb } from "../db/client.js";
import { integrationConnections } from "../db/schema.js";
import { discoverRegisteredWordPressTools } from "../integrations/wordpress/discovery.js";
import { fail, internalError, ok } from "./response.js";

const uuid = z.string().uuid();

function publicConnection(row: typeof integrationConnections.$inferSelect) {
  const { encryptedSecretRef: _secretRef, ...safe } = row;
  return safe;
}

function localHealthUrl(connection: typeof integrationConnections.$inferSelect): URL | null {
  const healthUrl = connection.config && typeof connection.config.healthUrl === "string" ? connection.config.healthUrl : null;
  if (!healthUrl) return null;
  try {
    const url = new URL(healthUrl);
    const allowedHost = url.hostname === "127.0.0.1" || url.hostname === "localhost" || url.hostname === "::1";
    return url.protocol === "http:" && allowedHost ? url : null;
  } catch {
    return null;
  }
}

export function createIntegrationsRouter() {
  const router = Router();

  router.get("/", requirePermission("integrations.read"), async (_request, response) => {
    try {
      const rows = await getDb().select().from(integrationConnections).orderBy(integrationConnections.name);
      return ok(response, { integrations: rows.map(publicConnection) });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.get("/:id", requirePermission("integrations.read"), async (request, response) => {
    try {
      const id = uuid.safeParse(request.params.id);
      if (!id.success) return fail(response, 400, "INVALID_INTEGRATION_ID", "Invalid integration id");
      const [row] = await getDb().select().from(integrationConnections).where(eq(integrationConnections.id, id.data)).limit(1);
      if (!row) return fail(response, 404, "INTEGRATION_NOT_FOUND", "Integration not found");
      return ok(response, { integration: publicConnection(row) });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.post("/:id/health-check", requirePermission("integrations.manage"), async (request, response) => {
    try {
      const id = uuid.safeParse(request.params.id);
      if (!id.success) return fail(response, 400, "INVALID_INTEGRATION_ID", "Invalid integration id");
      const db = getDb();
      const [connection] = await db.select().from(integrationConnections).where(eq(integrationConnections.id, id.data)).limit(1);
      if (!connection) return fail(response, 404, "INTEGRATION_NOT_FOUND", "Integration not found");
      const url = localHealthUrl(connection);
      if (!url) return fail(response, 400, "HEALTH_ENDPOINT_NOT_ALLOWED", "A localhost health endpoint is required in integration config");

      const now = new Date();
      let healthy = false;
      let statusCode: number | null = null;
      try {
        const result = await fetch(url, { method: "GET", signal: AbortSignal.timeout(5000) });
        statusCode = result.status;
        healthy = result.ok;
      } catch {
        healthy = false;
      }

      const [updated] = await db
        .update(integrationConnections)
        .set({
          status: healthy ? "connected" : "degraded",
          lastHealthAt: now,
          ...(healthy ? { lastSuccessAt: now } : {}),
          updatedAt: now,
        })
        .where(eq(integrationConnections.id, connection.id))
        .returning();

      const req = request as AuthenticatedRequest;
      await recordActivity({
        actorType: "user",
        actorId: req.auth?.userId,
        actorLabel: req.auth?.displayName,
        entityType: "integration",
        entityId: connection.id,
        action: healthy ? "integration.health_succeeded" : "integration.health_failed",
        summary: `Integration health check: ${connection.name}`,
        metadata: { statusCode },
      });

      return ok(response, { integration: publicConnection(updated), healthy, statusCode });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.post("/:id/discover-tools", requirePermission("integrations.manage"), async (request, response) => {
    const id = uuid.safeParse(request.params.id);
    if (!id.success) return fail(response, 400, "INVALID_INTEGRATION_ID", "Invalid integration id");

    const db = getDb();
    try {
      const [connection] = await db.select().from(integrationConnections).where(eq(integrationConnections.id, id.data)).limit(1);
      if (!connection) return fail(response, 404, "INTEGRATION_NOT_FOUND", "Integration not found");
      if (connection.type !== "wordpress_mcp") {
        return fail(response, 400, "DISCOVERY_NOT_SUPPORTED", "Tool discovery is currently supported only for WordPress MCP");
      }

      const discovery = await discoverRegisteredWordPressTools({ type: connection.type, endpoint: connection.endpoint });
      const now = new Date();
      const [updated] = await db
        .update(integrationConnections)
        .set({ status: "connected", lastHealthAt: now, lastSuccessAt: now, updatedAt: now })
        .where(eq(integrationConnections.id, connection.id))
        .returning();

      const req = request as AuthenticatedRequest;
      await recordActivity({
        actorType: "user",
        actorId: req.auth?.userId,
        actorLabel: req.auth?.displayName,
        entityType: "integration",
        entityId: connection.id,
        action: "integration.tools_discovered",
        summary: `Discovered ${discovery.toolCount} read-only-visible tools from ${connection.name}`,
        metadata: { toolCount: discovery.toolCount, mode: discovery.mode },
      });

      return ok(response, { integration: publicConnection(updated), discovery });
    } catch (error) {
      const now = new Date();
      await db
        .update(integrationConnections)
        .set({ status: "degraded", lastHealthAt: now, updatedAt: now })
        .where(eq(integrationConnections.id, id.data))
        .catch(() => undefined);

      const req = request as AuthenticatedRequest;
      await recordActivity({
        actorType: "user",
        actorId: req.auth?.userId,
        actorLabel: req.auth?.displayName,
        entityType: "integration",
        entityId: id.data,
        action: "integration.tools_discovery_failed",
        summary: "WordPress MCP tool discovery failed",
      }).catch(() => undefined);

      return fail(response, 502, "WORDPRESS_DISCOVERY_FAILED", "WordPress MCP tool discovery failed");
    }
  });

  return router;
}
