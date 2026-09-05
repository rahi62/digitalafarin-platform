import { Router } from "express";
import { z } from "zod";
import { recordActivity } from "../activity/service.js";
import { requirePermission, type AuthenticatedRequest } from "../auth/middleware.js";
import { approve, getApproval, listApprovals, reject, requestApproval } from "../domain/approvals/service.js";
import { fail, internalError, ok } from "./response.js";

const uuid = z.string().uuid();
const requestSchema = z.object({
  projectId: uuid,
  taskId: uuid.optional(),
  actionType: z.string().trim().min(1).max(120),
  integrationConnectionId: uuid.optional(),
  riskLevel: z.enum(["low", "medium", "high", "critical"]),
  payload: z.record(z.string(), z.unknown()).default({}),
  diffPreview: z.record(z.string(), z.unknown()).optional(),
});
const reviewSchema = z.object({ reason: z.string().max(5000).optional() });
const rejectSchema = z.object({ reason: z.string().trim().min(1).max(5000) });

export function createApprovalsRouter() {
  const router = Router();

  router.get("/", requirePermission("approvals.read"), async (_request, response) => {
    try {
      return ok(response, { approvals: await listApprovals() });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.get("/:id", requirePermission("approvals.read"), async (request, response) => {
    try {
      const id = uuid.safeParse(request.params.id);
      if (!id.success) return fail(response, 400, "INVALID_APPROVAL_ID", "Invalid approval id");
      const approval = await getApproval(id.data);
      if (!approval) return fail(response, 404, "APPROVAL_NOT_FOUND", "Approval not found");
      return ok(response, { approval });
    } catch (error) {
      return internalError(response, error);
    }
  });

  router.post("/", requirePermission("tasks.write"), async (request, response) => {
    try {
      const parsed = requestSchema.safeParse(request.body);
      if (!parsed.success) return fail(response, 400, "INVALID_INPUT", "Invalid approval request");
      const req = request as AuthenticatedRequest;
      const approval = await requestApproval({ ...parsed.data, requestedBy: req.auth?.userId });
      await recordActivity({
        actorType: "user",
        actorId: req.auth?.userId,
        actorLabel: req.auth?.displayName,
        projectId: approval.projectId,
        entityType: "approval",
        entityId: approval.id,
        action: "approval.requested",
        summary: `Approval requested: ${approval.actionType}`,
        metadata: { riskLevel: approval.riskLevel, taskId: approval.taskId },
      });
      return ok(response, { approval }, 201);
    } catch (error) {
      if (error instanceof Error && (error.message.includes("not required") || error.message.includes("not found"))) {
        return fail(response, 400, "APPROVAL_REQUEST_REJECTED", error.message);
      }
      return internalError(response, error);
    }
  });

  router.post("/:id/approve", requirePermission("approvals.review"), async (request, response) => {
    try {
      const id = uuid.safeParse(request.params.id);
      const parsed = reviewSchema.safeParse(request.body ?? {});
      if (!id.success || !parsed.success) return fail(response, 400, "INVALID_INPUT", "Invalid approval review");
      const req = request as AuthenticatedRequest;
      if (!req.auth) return fail(response, 401, "AUTH_REQUIRED", "Authentication required");
      const approval = await approve(id.data, req.auth.userId, parsed.data.reason);
      await recordActivity({
        actorType: "user",
        actorId: req.auth.userId,
        actorLabel: req.auth.displayName,
        projectId: approval.projectId,
        entityType: "approval",
        entityId: approval.id,
        action: "approval.approved",
        summary: `Approval approved: ${approval.actionType}`,
      });
      return ok(response, { approval });
    } catch (error) {
      if (error instanceof Error && error.message.includes("not pending")) return fail(response, 409, "INVALID_APPROVAL_STATE", error.message);
      return internalError(response, error);
    }
  });

  router.post("/:id/reject", requirePermission("approvals.review"), async (request, response) => {
    try {
      const id = uuid.safeParse(request.params.id);
      const parsed = rejectSchema.safeParse(request.body);
      if (!id.success || !parsed.success) return fail(response, 400, "INVALID_INPUT", "Invalid approval rejection");
      const req = request as AuthenticatedRequest;
      if (!req.auth) return fail(response, 401, "AUTH_REQUIRED", "Authentication required");
      const approval = await reject(id.data, req.auth.userId, parsed.data.reason);
      await recordActivity({
        actorType: "user",
        actorId: req.auth.userId,
        actorLabel: req.auth.displayName,
        projectId: approval.projectId,
        entityType: "approval",
        entityId: approval.id,
        action: "approval.rejected",
        summary: `Approval rejected: ${approval.actionType}`,
      });
      return ok(response, { approval });
    } catch (error) {
      if (error instanceof Error && error.message.includes("not pending")) return fail(response, 409, "INVALID_APPROVAL_STATE", error.message);
      return internalError(response, error);
    }
  });

  return router;
}
