import { Router } from "express";
import { z } from "zod";
import { recordActivity } from "../activity/service.js";
import { requirePermission } from "../auth/middleware.js";
import type { AuthenticatedRequest } from "../auth/middleware.js";
import {
  getProjectFromPostgres,
  listProjectsFromPostgres,
  upsertProjectInPostgres,
} from "../domain/projects/service.js";
import { routeParam } from "./params.js";
import { fail, internalError, ok } from "./response.js";

const projectIdSchema = z.string().uuid();
const slugSchema = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/).max(200);

const createProjectSchema = z.object({
  name: z.string().trim().min(1).max(200),
  slug: slugSchema.optional(),
  description: z.string().max(5000).optional(),
  goals: z.array(z.string().max(1000)).max(30).optional(),
  stack: z.array(z.string().max(100)).max(30).optional(),
  links: z.record(z.string().max(100), z.string().max(2000)).optional(),
  status: z.enum(["active", "paused", "archived"]).optional(),
});

const patchProjectSchema = createProjectSchema.partial();

function actor(request: AuthenticatedRequest) {
  return {
    actorType: "user" as const,
    actorId: request.auth?.userId,
    actorLabel: request.auth?.displayName,
  };
}

export function createProjectsRouter() {
  const router = Router();

  router.get("/", requirePermission("projects.read"), async (_request, response) => {
    try {
      return ok(response, { projects: await listProjectsFromPostgres() });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.post("/", requirePermission("projects.write"), async (request, response) => {
    try {
      const parsed = createProjectSchema.safeParse(request.body);
      if (!parsed.success) return fail(response, 400, "INVALID_INPUT", "Invalid project payload");
      const project = await upsertProjectInPostgres(parsed.data);
      const req = request as AuthenticatedRequest;
      await recordActivity({
        ...actor(req),
        projectId: project.id,
        entityType: "project",
        entityId: project.id,
        action: "project.created",
        summary: `Project created: ${project.name}`,
      });
      return ok(response, { project }, 201);
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.get("/:id", requirePermission("projects.read"), async (request, response) => {
    try {
      const parsedId = projectIdSchema.safeParse(request.params.id);
      if (!parsedId.success) return fail(response, 400, "INVALID_PROJECT_ID", "Invalid project id");
      const project = await getProjectFromPostgres(parsedId.data);
      if (!project) return fail(response, 404, "PROJECT_NOT_FOUND", "Project not found");
      return ok(response, { project });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.patch("/:id", requirePermission("projects.write"), async (request, response) => {
    try {
      const parsedId = projectIdSchema.safeParse(request.params.id);
      const parsedPatch = patchProjectSchema.safeParse(request.body);
      if (!parsedId.success || !parsedPatch.success) return fail(response, 400, "INVALID_INPUT", "Invalid project update");

      const current = await getProjectFromPostgres(parsedId.data);
      if (!current) return fail(response, 404, "PROJECT_NOT_FOUND", "Project not found");

      const project = await upsertProjectInPostgres({
        id: current.id,
        name: parsedPatch.data.name ?? current.name,
        slug: parsedPatch.data.slug ?? current.slug,
        description: parsedPatch.data.description ?? current.description,
        goals: parsedPatch.data.goals ?? current.goals,
        stack: parsedPatch.data.stack ?? current.stack,
        links: parsedPatch.data.links ?? current.links,
        status: parsedPatch.data.status ?? current.status,
      });

      const req = request as AuthenticatedRequest;
      await recordActivity({
        ...actor(req),
        projectId: project.id,
        entityType: "project",
        entityId: project.id,
        action: "project.updated",
        summary: `Project updated: ${project.name}`,
      });
      return ok(response, { project });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.get("/:id/tasks", requirePermission("tasks.read"), async (request, response) => {
    const project = await getProjectFromPostgres(routeParam(request.params.id));
    if (!project) return fail(response, 404, "PROJECT_NOT_FOUND", "Project not found");
    return ok(response, { tasks: project.tasks });
  });

  router.get("/:id/decisions", requirePermission("projects.read"), async (request, response) => {
    const project = await getProjectFromPostgres(routeParam(request.params.id));
    if (!project) return fail(response, 404, "PROJECT_NOT_FOUND", "Project not found");
    return ok(response, { decisions: project.decisions });
  });

  router.get("/:id/notes", requirePermission("projects.read"), async (request, response) => {
    const project = await getProjectFromPostgres(routeParam(request.params.id));
    if (!project) return fail(response, 404, "PROJECT_NOT_FOUND", "Project not found");
    return ok(response, { notes: project.notes });
  });

  return router;
}
