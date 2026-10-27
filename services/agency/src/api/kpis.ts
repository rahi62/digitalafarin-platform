import { Router } from "express";
import { desc, eq } from "drizzle-orm";
import { z } from "zod";
import { recordActivity } from "../activity/service.js";
import { requirePermission, type AuthenticatedRequest } from "../auth/middleware.js";
import { getDb } from "../db/client.js";
import { kpiDefinitions, kpiValues } from "../db/schema.js";
import { fail, internalError, ok } from "./response.js";

const uuid = z.string().uuid();
const valueSchema = z.object({
  kpiDefinitionId: uuid,
  projectId: uuid.nullable().optional(),
  departmentId: uuid.nullable().optional(),
  value: z.union([z.number(), z.string().regex(/^-?\d+(?:\.\d+)?$/)]).transform(String),
  periodStart: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  periodEnd: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  source: z.string().trim().min(1).max(120),
  metadata: z.record(z.string(), z.unknown()).optional(),
});

export function createKpisRouter() {
  const router = Router();

  router.get("/", requirePermission("kpis.read"), async (request, response) => {
    try {
      const db = getDb();
      const definitions = await db.select().from(kpiDefinitions).orderBy(kpiDefinitions.name);
      const projectId = typeof request.query.projectId === "string" ? request.query.projectId : undefined;
      const values = projectId
        ? await db.select().from(kpiValues).where(eq(kpiValues.projectId, projectId)).orderBy(desc(kpiValues.periodEnd)).limit(500)
        : await db.select().from(kpiValues).orderBy(desc(kpiValues.periodEnd)).limit(500);
      return ok(response, { definitions, values });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.post("/values", requirePermission("kpis.write"), async (request, response) => {
    try {
      const parsed = valueSchema.safeParse(request.body);
      if (!parsed.success) return fail(response, 400, "INVALID_INPUT", "Invalid KPI value");
      const db = getDb();
      const [definition] = await db
        .select({ id: kpiDefinitions.id, name: kpiDefinitions.name })
        .from(kpiDefinitions)
        .where(eq(kpiDefinitions.id, parsed.data.kpiDefinitionId))
        .limit(1);
      if (!definition) return fail(response, 404, "KPI_NOT_FOUND", "KPI definition not found");

      const [value] = await db.insert(kpiValues).values(parsed.data).returning();
      const req = request as AuthenticatedRequest;
      await recordActivity({
        actorType: "user",
        actorId: req.auth?.userId,
        actorLabel: req.auth?.displayName,
        projectId: parsed.data.projectId ?? undefined,
        entityType: "kpi_value",
        entityId: value.id,
        action: "kpi.recorded",
        summary: `KPI recorded: ${definition.name}`,
        metadata: { value: parsed.data.value, source: parsed.data.source },
      });
      return ok(response, { value }, 201);
    } catch (error) {
      return internalError(response, error);
    }
  });

  return router;
}
