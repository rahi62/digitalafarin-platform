import { Router } from "express";
import { desc } from "drizzle-orm";
import { requirePermission } from "../auth/middleware.js";
import { getDb } from "../db/client.js";
import { activityLogs, approvals, departments, projects, tasks } from "../db/schema.js";
import { internalError, ok } from "./response.js";

export function createDashboardRouter() {
  const router = Router();

  router.get("/summary", requirePermission("dashboard.read"), async (_request, response) => {
    try {
      const db = getDb();
      const [projectRows, taskRows, approvalRows, departmentRows, recentActivity] = await Promise.all([
        db.select().from(projects),
        db.select().from(tasks),
        db.select().from(approvals),
        db.select().from(departments),
        db.select().from(activityLogs).orderBy(desc(activityLogs.createdAt)).limit(12),
      ]);

      const departmentWorkload = departmentRows.map((department) => {
        const owned = taskRows.filter((task) => task.departmentId === department.id);
        return {
          id: department.id,
          slug: department.slug,
          name: department.name,
          openTasks: owned.filter((task) => task.status === "todo" || task.status === "doing" || task.status === "blocked").length,
          blockedTasks: owned.filter((task) => task.status === "blocked").length,
        };
      });

      return ok(response, {
        counters: {
          activeProjects: projectRows.filter((project) => project.status === "active").length,
          criticalTasks: taskRows.filter((task) => task.priority === "critical" && task.status !== "done").length,
          blockedTasks: taskRows.filter((task) => task.status === "blocked").length,
          pendingApprovals: approvalRows.filter((approval) => approval.status === "pending").length,
        },
        projectHealth: projectRows
          .filter((project) => project.status === "active")
          .map((project) => ({ id: project.id, name: project.name, slug: project.slug, health: project.health, priority: project.priority })),
        departmentWorkload,
        recentActivity,
        upcomingDeadlines: taskRows
          .filter((task) => task.dueDate && task.status !== "done")
          .sort((a, b) => String(a.dueDate).localeCompare(String(b.dueDate)))
          .slice(0, 10),
      });
    } catch (error) {
      return internalError(response, error);
    }
  });

  return router;
}
