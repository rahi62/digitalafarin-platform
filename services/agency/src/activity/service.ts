import { desc, eq } from "drizzle-orm";
import { getDb } from "../db/client.js";
import { activityLogs } from "../db/schema.js";

export type ActivityInput = {
  actorType: "user" | "chatgpt" | "system" | "integration";
  actorId?: string;
  actorLabel?: string;
  projectId?: string;
  entityType: string;
  entityId?: string;
  action: string;
  summary: string;
  metadata?: Record<string, unknown>;
};

export async function recordActivity(input: ActivityInput) {
  const db = getDb();
  const [row] = await db
    .insert(activityLogs)
    .values({
      actorType: input.actorType,
      actorId: input.actorId,
      actorLabel: input.actorLabel,
      projectId: input.projectId,
      entityType: input.entityType,
      entityId: input.entityId,
      action: input.action,
      summary: input.summary,
      metadata: input.metadata,
    })
    .returning();
  return row;
}

export async function listActivity(options: { projectId?: string; limit?: number } = {}) {
  const db = getDb();
  const limit = Math.min(Math.max(options.limit ?? 50, 1), 200);
  const query = db.select().from(activityLogs);
  return options.projectId
    ? query.where(eq(activityLogs.projectId, options.projectId)).orderBy(desc(activityLogs.createdAt)).limit(limit)
    : query.orderBy(desc(activityLogs.createdAt)).limit(limit);
}
