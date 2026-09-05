import { Router } from "express";
import { eq } from "drizzle-orm";
import { z } from "zod";
import { requirePermission } from "../auth/middleware.js";
import { getDb } from "../db/client.js";
import { departmentRoles, departments, tasks, workflowSteps, workflows } from "../db/schema.js";
import { fail, internalError, ok } from "./response.js";

const uuid = z.string().uuid();

export function createDepartmentsRouter() {
  const router = Router();

  router.get("/", requirePermission("departments.read"), async (_request, response) => {
    try {
      const rows = await getDb().select().from(departments).orderBy(departments.name);
      return ok(response, { departments: rows });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.get("/:id", requirePermission("departments.read"), async (request, response) => {
    try {
      const id = uuid.safeParse(request.params.id);
      if (!id.success) return fail(response, 400, "INVALID_DEPARTMENT_ID", "Invalid department id");
      const db = getDb();
      const [department] = await db.select().from(departments).where(eq(departments.id, id.data)).limit(1);
      if (!department) return fail(response, 404, "DEPARTMENT_NOT_FOUND", "Department not found");
      const [roles, departmentTasks, departmentWorkflows] = await Promise.all([
        db.select().from(departmentRoles).where(eq(departmentRoles.departmentId, id.data)).orderBy(departmentRoles.name),
        db.select().from(tasks).where(eq(tasks.departmentId, id.data)).orderBy(tasks.updatedAt),
        db.select().from(workflows).where(eq(workflows.departmentId, id.data)).orderBy(workflows.name),
      ]);
      return ok(response, { department, roles, tasks: departmentTasks, workflows: departmentWorkflows });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.get("/:id/tasks", requirePermission("tasks.read"), async (request, response) => {
    try {
      const id = uuid.safeParse(request.params.id);
      if (!id.success) return fail(response, 400, "INVALID_DEPARTMENT_ID", "Invalid department id");
      const rows = await getDb().select().from(tasks).where(eq(tasks.departmentId, id.data)).orderBy(tasks.updatedAt);
      return ok(response, { tasks: rows });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.get("/:id/workflows", requirePermission("departments.read"), async (request, response) => {
    try {
      const id = uuid.safeParse(request.params.id);
      if (!id.success) return fail(response, 400, "INVALID_DEPARTMENT_ID", "Invalid department id");
      const db = getDb();
      const workflowRows = await db.select().from(workflows).where(eq(workflows.departmentId, id.data)).orderBy(workflows.name);
      const result = [];
      for (const workflow of workflowRows) {
        const steps = await db.select().from(workflowSteps).where(eq(workflowSteps.workflowId, workflow.id)).orderBy(workflowSteps.position);
        result.push({ ...workflow, steps });
      }
      return ok(response, { workflows: result });
    } catch (error) {
      return internalError(response, error);
    }
  });

  return router;
}
