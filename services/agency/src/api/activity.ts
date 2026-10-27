import { Router } from "express";
import { requirePermission } from "../auth/middleware.js";
import { listActivity } from "../activity/service.js";
import { internalError, ok } from "./response.js";

export function createActivityRouter() {
  const router = Router();

  router.get("/", requirePermission("activity.read"), async (request, response) => {
    try {
      const projectId = typeof request.query.projectId === "string" ? request.query.projectId : undefined;
      const rawLimit = typeof request.query.limit === "string" ? Number(request.query.limit) : 50;
      const limit = Number.isFinite(rawLimit) ? rawLimit : 50;
      return ok(response, { activity: await listActivity({ projectId, limit }) });
    } catch (error) {
      return internalError(response, error);
    }
  });

  return router;
}
