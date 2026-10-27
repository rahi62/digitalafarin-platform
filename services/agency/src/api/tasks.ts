import { Router } from "express";
import { z } from "zod";
import { recordActivity } from "../activity/service.js";
import { requirePermission, type AuthenticatedRequest } from "../auth/middleware.js";
import { createAdminTask, getAdminTask, listAdminTasks, updateAdminTask } from "../domain/tasks/admin-service.js";
import { fail, internalError, ok } from "./response.js";

const uuid = z.string().uuid();
const nullableUuid = uuid.nullable();
const createSchema = z.object({
  projectId: uuid,
  departmentId: nullableUuid.optional(),
  title: z.string().trim().min(1).max(300),
  description: z.string().max(10000).nullable().optional(),
  status: z.enum(["todo", "doing", "done", "blocked"]).optional(),
  priority: z.enum(["low", "medium", "high", "critical"]).optional(),
  riskLevel: z.enum(["low", "medium", "high", "critical"]).optional(),
  ownerId: nullableUuid.optional(),
  ownerLabel: z.string().max(100).nullable().optional(),
  executorType: z.enum(["manual", "wordpress_mcp", "github", "automation", "other"]).optional(),
  integrationConnectionId: nullableUuid.optional(),
  approvalRequired: z.boolean().optional(),
  expectedImpact: z.string().max(5000).nullable().optional(),
  effort: z.string().max(100).nullable().optional(),
  dueDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable().optional(),
});
const patchSchema = createSchema.omit({ projectId: true }).partial();

function actor(request: AuthenticatedRequest) {
  return { actorType: "user" as const, actorId: request.auth?.userId, actorLabel: request.auth?.displayName };
}

export function createTasksRouter() {
  const router = Router();

  router.get("/", requirePermission("tasks.read"), async (request, response) => {
    try {
      let rows = await listAdminTasks();
      const filters = {
        projectId: typeof request.query.projectId === "string" ? request.query.projectId : undefined,
        departmentId: typeof request.query.departmentId === "string" ? request.query.departmentId : undefined,
        status: typeof request.query.status === "string" ? request.query.status : undefined,
        priority: typeof request.query.priority === "string" ? request.query.priority : undefined,
        riskLevel: typeof request.query.riskLevel === "string" ? request.query.riskLevel : undefined,
        executorType: typeof request.query.executorType === "string" ? request.query.executorType : undefined,
      };
      rows = rows.filter((row) =>
        (!filters.projectId || row.projectId === filters.projectId) &&
        (!filters.departmentId || row.departmentId === filters.departmentId) &&
        (!filters.status || row.status === filters.status) &&
        (!filters.priority || row.priority === filters.priority) &&
        (!filters.riskLevel || row.riskLevel === filters.riskLevel) &&
        (!filters.executorType || row.executorType === filters.executorType),
      );
      return ok(response, { tasks: rows.slice(0, 500) });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.get("/:id", requirePermission("tasks.read"), async (request, response) => {
    try {
      const id = uuid.safeParse(request.params.id);
      if (!id.success) return fail(response, 400, "INVALID_TASK_ID", "Invalid task id");
      const task = await getAdminTask(id.data);
      if (!task) return fail(response, 404, "TASK_NOT_FOUND", "Task not found");
      return ok(response, { task });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.post("/", requirePermission("tasks.write"), async (request, response) => {
    try {
      const parsed = createSchema.safeParse(request.body);
      if (!parsed.success) return fail(response, 400, "INVALID_INPUT", "Invalid task payload");
      const req = request as AuthenticatedRequest;
      const task = await createAdminTask({ ...parsed.data, createdBy: req.auth?.userId ?? null });
      await recordActivity({
        ...actor(req),
        projectId: task.projectId,
        entityType: "task",
        entityId: task.id,
        action: "task.created",
        summary: `Task created: ${task.title}`,
        metadata: { priority: task.priority, riskLevel: task.riskLevel, executorType: task.executorType },
      });
      return ok(response, { task }, 201);
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.patch("/:id", requirePermission("tasks.write"), async (request, response) => {
    try {
      const id = uuid.safeParse(request.params.id);
      const parsed = patchSchema.safeParse(request.body);
      if (!id.success || !parsed.success) return fail(response, 400, "INVALID_INPUT", "Invalid task update");
      const req = request as AuthenticatedRequest;
      const task = await updateAdminTask(id.data, parsed.data);
      if (!task) return fail(response, 404, "TASK_NOT_FOUND", "Task not found");
      await recordActivity({
        ...actor(req),
        projectId: task.projectId,
        entityType: "task",
        entityId: task.id,
        action: task.status === "done" ? "task.completed" : "task.updated",
        summary: `Task updated: ${task.title}`,
        metadata: { status: task.status, priority: task.priority, riskLevel: task.riskLevel },
      });
      return ok(response, { task });
    } catch (error) {
      return internalError(response, error);
    }
  });

  return router;
}
