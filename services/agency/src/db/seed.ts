import { eq } from "drizzle-orm";
import { closeDb, getDb } from "./client.js";
import {
  departmentRoles,
  departments,
  integrationConnections,
  kpiDefinitions,
  permissions,
  rolePermissions,
  roles,
  userRoles,
  users,
  workflows,
  workflowSteps,
} from "./schema.js";
import { hashPassword } from "../auth/password.js";
import { permissionKeys, type PermissionKey } from "../auth/permissions.js";
import { departmentSeedData, seoKpiDefinitions, seoRoleDefinitions } from "../domain/departments/seed-data.js";
import { integrationSeedData } from "../domain/integrations/seed-data.js";
import { seoWorkflowDefinition } from "../domain/workflows/seo.js";

const roleDefinitions: Array<{ slug: string; name: string; permissions: PermissionKey[] }> = [
  { slug: "super_admin", name: "Super Admin", permissions: [...permissionKeys] },
  {
    slug: "project_manager",
    name: "Project Manager",
    permissions: [
      "dashboard.read",
      "projects.read",
      "projects.write",
      "tasks.read",
      "tasks.write",
      "departments.read",
      "approvals.read",
      "activity.read",
      "integrations.read",
      "kpis.read",
    ],
  },
  {
    slug: "seo_manager",
    name: "SEO Manager",
    permissions: [
      "dashboard.read",
      "projects.read",
      "projects.write",
      "tasks.read",
      "tasks.write",
      "departments.read",
      "approvals.read",
      "activity.read",
      "integrations.read",
      "kpis.read",
      "kpis.write",
    ],
  },
  {
    slug: "developer",
    name: "Developer",
    permissions: [
      "dashboard.read",
      "projects.read",
      "tasks.read",
      "tasks.write",
      "departments.read",
      "approvals.read",
      "activity.read",
      "integrations.read",
      "kpis.read",
    ],
  },
  {
    slug: "viewer",
    name: "Viewer",
    permissions: [
      "dashboard.read",
      "projects.read",
      "tasks.read",
      "departments.read",
      "approvals.read",
      "activity.read",
      "integrations.read",
      "kpis.read",
    ],
  },
];

async function seedAccessControl(): Promise<void> {
  const db = getDb();

  for (const key of permissionKeys) {
    await db
      .insert(permissions)
      .values({ key, description: key })
      .onConflictDoNothing({ target: permissions.key });
  }

  for (const role of roleDefinitions) {
    await db.insert(roles).values({ slug: role.slug, name: role.name }).onConflictDoNothing({ target: roles.slug });
  }

  const permissionRows = await db.select().from(permissions);
  const roleRows = await db.select().from(roles);
  const permissionByKey = new Map(permissionRows.map((row) => [row.key, row]));
  const roleBySlug = new Map(roleRows.map((row) => [row.slug, row]));

  for (const definition of roleDefinitions) {
    const role = roleBySlug.get(definition.slug);
    if (!role) throw new Error(`Seeded role not found: ${definition.slug}`);
    for (const key of definition.permissions) {
      const permission = permissionByKey.get(key);
      if (!permission) throw new Error(`Seeded permission not found: ${key}`);
      await db
        .insert(rolePermissions)
        .values({ roleId: role.id, permissionId: permission.id })
        .onConflictDoNothing();
    }
  }
}

async function seedDepartments(): Promise<void> {
  const db = getDb();

  for (const department of departmentSeedData) {
    await db
      .insert(departments)
      .values({ slug: department.slug, name: department.name, mission: department.mission, status: "active" })
      .onConflictDoNothing({ target: departments.slug });
  }

  const [seoDepartment] = await db.select().from(departments).where(eq(departments.slug, "seo")).limit(1);
  if (!seoDepartment) throw new Error("SEO department seed failed");

  for (const role of seoRoleDefinitions) {
    await db
      .insert(departmentRoles)
      .values({
        departmentId: seoDepartment.id,
        slug: role.slug,
        name: role.name,
        mission: role.mission,
        responsibilities: [...role.responsibilities],
      })
      .onConflictDoNothing({ target: [departmentRoles.departmentId, departmentRoles.slug] });
  }

  for (const kpi of seoKpiDefinitions) {
    await db
      .insert(kpiDefinitions)
      .values({
        slug: kpi.slug,
        name: kpi.name,
        unit: kpi.unit,
        direction: kpi.direction,
        departmentId: seoDepartment.id,
      })
      .onConflictDoNothing({ target: kpiDefinitions.slug });
  }

  await db
    .insert(workflows)
    .values({
      departmentId: seoDepartment.id,
      slug: seoWorkflowDefinition.slug,
      name: seoWorkflowDefinition.name,
      description: seoWorkflowDefinition.description,
      status: seoWorkflowDefinition.status,
    })
    .onConflictDoNothing({ target: workflows.slug });

  const [seoWorkflow] = await db.select().from(workflows).where(eq(workflows.slug, seoWorkflowDefinition.slug)).limit(1);
  if (!seoWorkflow) throw new Error("SEO workflow seed failed");

  for (const step of seoWorkflowDefinition.steps) {
    await db
      .insert(workflowSteps)
      .values({
        workflowId: seoWorkflow.id,
        position: step.position,
        name: step.name,
        stepType: step.stepType,
        config: step.config,
      })
      .onConflictDoNothing({ target: [workflowSteps.workflowId, workflowSteps.position] });
  }
}

async function seedIntegrations(): Promise<void> {
  const db = getDb();
  for (const integration of integrationSeedData) {
    await db
      .insert(integrationConnections)
      .values({
        slug: integration.slug,
        name: integration.name,
        type: integration.type,
        endpoint: integration.endpoint,
        config: integration.config,
        status: "disconnected",
      })
      .onConflictDoNothing({ target: integrationConnections.slug });
  }
}

export async function seedCoreData(): Promise<void> {
  await seedAccessControl();
  await seedDepartments();
  await seedIntegrations();
}

export async function bootstrapSuperAdmin(): Promise<void> {
  const email = (process.env.BOOTSTRAP_ADMIN_EMAIL ?? "").trim().toLowerCase();
  const password = process.env.BOOTSTRAP_ADMIN_PASSWORD ?? "";
  const displayName = (process.env.BOOTSTRAP_ADMIN_NAME ?? "DigitalAfarin Admin").trim();
  if (!email && !password) return;
  if (!email || !password) throw new Error("BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD must be provided together");

  const db = getDb();
  const passwordHash = await hashPassword(password);

  await db
    .insert(users)
    .values({ email, passwordHash, displayName, status: "active" })
    .onConflictDoNothing({ target: users.email });

  const [user] = await db.select().from(users).where(eq(users.email, email)).limit(1);
  const [role] = await db.select().from(roles).where(eq(roles.slug, "super_admin")).limit(1);
  if (!user || !role) throw new Error("Unable to resolve super admin seed records");

  await db.insert(userRoles).values({ userId: user.id, roleId: role.id }).onConflictDoNothing();
}

async function main() {
  await seedCoreData();
  await bootstrapSuperAdmin();
  console.log("Agency core seed completed.");
}

if (process.argv[1]?.endsWith("seed.ts") || process.argv[1]?.endsWith("seed.js")) {
  main()
    .catch((error) => {
      console.error(error instanceof Error ? error.message : error);
      process.exitCode = 1;
    })
    .finally(async () => {
      await closeDb();
    });
}
