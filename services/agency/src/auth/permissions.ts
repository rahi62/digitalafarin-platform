import { eq } from "drizzle-orm";
import { getDb } from "../db/client.js";
import { permissions, rolePermissions, roles, userRoles } from "../db/schema.js";

export const permissionKeys = [
  "dashboard.read",
  "projects.read",
  "projects.write",
  "tasks.read",
  "tasks.write",
  "departments.read",
  "departments.write",
  "approvals.read",
  "approvals.review",
  "activity.read",
  "integrations.read",
  "integrations.manage",
  "kpis.read",
  "kpis.write",
  "users.read",
  "users.manage",
  "settings.manage",
] as const;

export type PermissionKey = (typeof permissionKeys)[number];

export async function getUserPermissions(userId: string): Promise<Set<PermissionKey>> {
  const db = getDb();
  const rows = await db
    .select({
      roleSlug: roles.slug,
      permissionKey: permissions.key,
    })
    .from(userRoles)
    .innerJoin(roles, eq(userRoles.roleId, roles.id))
    .leftJoin(rolePermissions, eq(rolePermissions.roleId, roles.id))
    .leftJoin(permissions, eq(rolePermissions.permissionId, permissions.id))
    .where(eq(userRoles.userId, userId));

  if (rows.some((row) => row.roleSlug === "super_admin")) return new Set(permissionKeys);

  const allowed = new Set<PermissionKey>();
  for (const row of rows) {
    if (row.permissionKey && permissionKeys.includes(row.permissionKey as PermissionKey)) {
      allowed.add(row.permissionKey as PermissionKey);
    }
  }
  return allowed;
}

export async function userHasPermission(userId: string, permission: PermissionKey): Promise<boolean> {
  const allowed = await getUserPermissions(userId);
  return allowed.has(permission);
}
