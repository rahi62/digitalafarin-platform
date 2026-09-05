import { Router } from "express";
import { createActivityRouter } from "./api/activity.js";
import { createApprovalsRouter } from "./api/approvals.js";
import { createAuthRouter } from "./api/auth.js";
import { createDashboardRouter } from "./api/dashboard.js";
import { createDepartmentsRouter } from "./api/departments.js";
import { createIntegrationsRouter } from "./api/integrations.js";
import { createKpisRouter } from "./api/kpis.js";
import { createProjectsRouter } from "./api/projects.js";
import { createTasksRouter } from "./api/tasks.js";
import { authenticateRequest } from "./auth/middleware.js";
import { requireCsrf } from "./auth/csrf.js";

export function createAdminApiRouter() {
  const router = Router();

  router.use("/auth", createAuthRouter());

  router.use(authenticateRequest);
  router.use(requireCsrf);

  router.use("/dashboard", createDashboardRouter());
  router.use("/projects", createProjectsRouter());
  router.use("/tasks", createTasksRouter());
  router.use("/departments", createDepartmentsRouter());
  router.use("/approvals", createApprovalsRouter());
  router.use("/integrations", createIntegrationsRouter());
  router.use("/activity", createActivityRouter());
  router.use("/kpis", createKpisRouter());

  return router;
}
