import {
  boolean,
  date,
  integer,
  jsonb,
  numeric,
  pgEnum,
  pgTable,
  primaryKey,
  text,
  timestamp,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";

export const userStatusEnum = pgEnum("user_status", ["active", "disabled"]);
export const departmentStatusEnum = pgEnum("department_status", ["active", "paused", "archived"]);
export const projectTypeEnum = pgEnum("project_type", ["internal", "client"]);
export const projectStatusEnum = pgEnum("project_status", ["active", "paused", "archived"]);
export const projectHealthEnum = pgEnum("project_health", ["healthy", "attention", "at_risk", "critical"]);
export const priorityEnum = pgEnum("priority", ["low", "medium", "high", "critical"]);
export const taskStatusEnum = pgEnum("task_status", ["todo", "doing", "done", "blocked"]);
export const riskLevelEnum = pgEnum("risk_level", ["low", "medium", "high", "critical"]);
export const executorTypeEnum = pgEnum("executor_type", ["manual", "wordpress_mcp", "github", "automation", "other"]);
export const approvalStatusEnum = pgEnum("approval_status", ["pending", "approved", "rejected", "expired", "cancelled"]);
export const executionStatusEnum = pgEnum("execution_status", ["queued", "running", "succeeded", "failed", "cancelled"]);
export const workflowStatusEnum = pgEnum("workflow_status", ["draft", "active", "archived"]);
export const workflowStepTypeEnum = pgEnum("workflow_step_type", ["manual", "analysis", "approval", "execution", "qa"]);
export const workflowRunStatusEnum = pgEnum("workflow_run_status", ["pending", "running", "succeeded", "failed", "cancelled"]);
export const integrationTypeEnum = pgEnum("integration_type", ["wordpress_mcp", "github", "gsc", "ga4", "other"]);
export const integrationStatusEnum = pgEnum("integration_status", ["connected", "degraded", "disconnected", "disabled"]);
export const kpiDirectionEnum = pgEnum("kpi_direction", ["increase", "decrease", "target"]);
export const activityActorTypeEnum = pgEnum("activity_actor_type", ["user", "chatgpt", "system", "integration"]);

export const users = pgTable(
  "users",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    email: text("email").notNull(),
    passwordHash: text("password_hash").notNull(),
    displayName: text("display_name").notNull(),
    status: userStatusEnum("status").notNull().default("active"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
    lastLoginAt: timestamp("last_login_at", { withTimezone: true }),
  },
  (table) => [uniqueIndex("users_email_unique").on(table.email)],
);

export const roles = pgTable(
  "roles",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    slug: text("slug").notNull(),
    name: text("name").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [uniqueIndex("roles_slug_unique").on(table.slug)],
);

export const permissions = pgTable(
  "permissions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    key: text("key").notNull(),
    description: text("description"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [uniqueIndex("permissions_key_unique").on(table.key)],
);

export const userRoles = pgTable(
  "user_roles",
  {
    userId: uuid("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
    roleId: uuid("role_id").notNull().references(() => roles.id, { onDelete: "cascade" }),
  },
  (table) => [primaryKey({ columns: [table.userId, table.roleId] })],
);

export const rolePermissions = pgTable(
  "role_permissions",
  {
    roleId: uuid("role_id").notNull().references(() => roles.id, { onDelete: "cascade" }),
    permissionId: uuid("permission_id").notNull().references(() => permissions.id, { onDelete: "cascade" }),
  },
  (table) => [primaryKey({ columns: [table.roleId, table.permissionId] })],
);

export const sessions = pgTable(
  "sessions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
    tokenHash: text("token_hash").notNull(),
    expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    lastSeenAt: timestamp("last_seen_at", { withTimezone: true }).notNull().defaultNow(),
    ipHash: text("ip_hash"),
    userAgent: text("user_agent"),
  },
  (table) => [uniqueIndex("sessions_token_hash_unique").on(table.tokenHash)],
);

export const departments = pgTable(
  "departments",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    slug: text("slug").notNull(),
    name: text("name").notNull(),
    mission: text("mission"),
    status: departmentStatusEnum("status").notNull().default("active"),
    leadUserId: uuid("lead_user_id").references(() => users.id, { onDelete: "set null" }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [uniqueIndex("departments_slug_unique").on(table.slug)],
);

export const departmentRoles = pgTable(
  "department_roles",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    departmentId: uuid("department_id").notNull().references(() => departments.id, { onDelete: "cascade" }),
    slug: text("slug").notNull(),
    name: text("name").notNull(),
    mission: text("mission"),
    responsibilities: jsonb("responsibilities").$type<string[]>(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [uniqueIndex("department_roles_department_slug_unique").on(table.departmentId, table.slug)],
);

export const departmentMembers = pgTable(
  "department_members",
  {
    departmentId: uuid("department_id").notNull().references(() => departments.id, { onDelete: "cascade" }),
    userId: uuid("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
    departmentRoleId: uuid("department_role_id").references(() => departmentRoles.id, { onDelete: "set null" }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [primaryKey({ columns: [table.departmentId, table.userId] })],
);

export const integrationConnections = pgTable(
  "integration_connections",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    slug: text("slug").notNull(),
    name: text("name").notNull(),
    type: integrationTypeEnum("type").notNull(),
    status: integrationStatusEnum("status").notNull().default("disconnected"),
    endpoint: text("endpoint"),
    config: jsonb("config").$type<Record<string, unknown>>(),
    encryptedSecretRef: text("encrypted_secret_ref"),
    lastHealthAt: timestamp("last_health_at", { withTimezone: true }),
    lastSuccessAt: timestamp("last_success_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [uniqueIndex("integration_connections_slug_unique").on(table.slug)],
);

export const projects = pgTable(
  "projects",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    name: text("name").notNull(),
    slug: text("slug").notNull(),
    type: projectTypeEnum("type").notNull().default("internal"),
    status: projectStatusEnum("status").notNull().default("active"),
    health: projectHealthEnum("health").notNull().default("healthy"),
    priority: priorityEnum("priority").notNull().default("medium"),
    summary: text("summary"),
    goals: jsonb("goals").$type<string[]>().notNull(),
    stack: jsonb("stack").$type<string[]>().notNull(),
    links: jsonb("links").$type<Record<string, string>>().notNull(),
    ownerId: uuid("owner_id").references(() => users.id, { onDelete: "set null" }),
    primaryDepartmentId: uuid("primary_department_id").references(() => departments.id, { onDelete: "set null" }),
    startDate: date("start_date"),
    targetDate: date("target_date"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [uniqueIndex("projects_slug_unique").on(table.slug)],
);

export const projectMembers = pgTable(
  "project_members",
  {
    projectId: uuid("project_id").notNull().references(() => projects.id, { onDelete: "cascade" }),
    userId: uuid("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
    projectRole: text("project_role"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [primaryKey({ columns: [table.projectId, table.userId] })],
);

export const decisions = pgTable("decisions", {
  id: uuid("id").primaryKey().defaultRandom(),
  projectId: uuid("project_id").notNull().references(() => projects.id, { onDelete: "cascade" }),
  title: text("title").notNull(),
  decision: text("decision").notNull(),
  rationale: text("rationale"),
  createdBy: uuid("created_by").references(() => users.id, { onDelete: "set null" }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const notes = pgTable("notes", {
  id: uuid("id").primaryKey().defaultRandom(),
  projectId: uuid("project_id").notNull().references(() => projects.id, { onDelete: "cascade" }),
  text: text("text").notNull(),
  createdBy: uuid("created_by").references(() => users.id, { onDelete: "set null" }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const tasks = pgTable("tasks", {
  id: uuid("id").primaryKey().defaultRandom(),
  projectId: uuid("project_id").notNull().references(() => projects.id, { onDelete: "cascade" }),
  departmentId: uuid("department_id").references(() => departments.id, { onDelete: "set null" }),
  title: text("title").notNull(),
  description: text("description"),
  status: taskStatusEnum("status").notNull().default("todo"),
  priority: priorityEnum("priority").notNull().default("medium"),
  riskLevel: riskLevelEnum("risk_level").notNull().default("low"),
  ownerId: uuid("owner_id").references(() => users.id, { onDelete: "set null" }),
  ownerLabel: text("owner_label"),
  executorType: executorTypeEnum("executor_type").notNull().default("manual"),
  integrationConnectionId: uuid("integration_connection_id").references(() => integrationConnections.id, { onDelete: "set null" }),
  approvalRequired: boolean("approval_required").notNull().default(false),
  expectedImpact: text("expected_impact"),
  effort: text("effort"),
  dueDate: date("due_date"),
  createdBy: uuid("created_by").references(() => users.id, { onDelete: "set null" }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  completedAt: timestamp("completed_at", { withTimezone: true }),
});

export const approvals = pgTable("approvals", {
  id: uuid("id").primaryKey().defaultRandom(),
  projectId: uuid("project_id").notNull().references(() => projects.id, { onDelete: "cascade" }),
  taskId: uuid("task_id").references(() => tasks.id, { onDelete: "set null" }),
  actionType: text("action_type").notNull(),
  integrationConnectionId: uuid("integration_connection_id").references(() => integrationConnections.id, { onDelete: "set null" }),
  riskLevel: riskLevelEnum("risk_level").notNull(),
  status: approvalStatusEnum("status").notNull().default("pending"),
  requestedBy: uuid("requested_by").references(() => users.id, { onDelete: "set null" }),
  requestedAt: timestamp("requested_at", { withTimezone: true }).notNull().defaultNow(),
  reviewedBy: uuid("reviewed_by").references(() => users.id, { onDelete: "set null" }),
  reviewedAt: timestamp("reviewed_at", { withTimezone: true }),
  reason: text("reason"),
  payload: jsonb("payload").$type<Record<string, unknown>>().notNull(),
  diffPreview: jsonb("diff_preview").$type<Record<string, unknown>>(),
});

export const executions = pgTable("executions", {
  id: uuid("id").primaryKey().defaultRandom(),
  approvalId: uuid("approval_id").references(() => approvals.id, { onDelete: "set null" }),
  taskId: uuid("task_id").references(() => tasks.id, { onDelete: "set null" }),
  integrationConnectionId: uuid("integration_connection_id").references(() => integrationConnections.id, { onDelete: "set null" }),
  executorType: executorTypeEnum("executor_type").notNull(),
  status: executionStatusEnum("status").notNull().default("queued"),
  requestPayload: jsonb("request_payload").$type<Record<string, unknown>>().notNull(),
  resultPayload: jsonb("result_payload").$type<Record<string, unknown>>(),
  errorMessage: text("error_message"),
  retryCount: integer("retry_count").notNull().default(0),
  startedAt: timestamp("started_at", { withTimezone: true }),
  finishedAt: timestamp("finished_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const workflows = pgTable(
  "workflows",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    departmentId: uuid("department_id").references(() => departments.id, { onDelete: "set null" }),
    slug: text("slug").notNull(),
    name: text("name").notNull(),
    description: text("description"),
    status: workflowStatusEnum("status").notNull().default("draft"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [uniqueIndex("workflows_slug_unique").on(table.slug)],
);

export const workflowSteps = pgTable(
  "workflow_steps",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    workflowId: uuid("workflow_id").notNull().references(() => workflows.id, { onDelete: "cascade" }),
    position: integer("position").notNull(),
    name: text("name").notNull(),
    stepType: workflowStepTypeEnum("step_type").notNull(),
    config: jsonb("config").$type<Record<string, unknown>>().notNull(),
  },
  (table) => [uniqueIndex("workflow_steps_workflow_position_unique").on(table.workflowId, table.position)],
);

export const workflowRuns = pgTable("workflow_runs", {
  id: uuid("id").primaryKey().defaultRandom(),
  workflowId: uuid("workflow_id").notNull().references(() => workflows.id, { onDelete: "cascade" }),
  projectId: uuid("project_id").notNull().references(() => projects.id, { onDelete: "cascade" }),
  status: workflowRunStatusEnum("status").notNull().default("pending"),
  currentStep: integer("current_step").notNull().default(0),
  startedAt: timestamp("started_at", { withTimezone: true }).notNull().defaultNow(),
  finishedAt: timestamp("finished_at", { withTimezone: true }),
});

export const workflowStepRuns = pgTable("workflow_step_runs", {
  id: uuid("id").primaryKey().defaultRandom(),
  workflowRunId: uuid("workflow_run_id").notNull().references(() => workflowRuns.id, { onDelete: "cascade" }),
  workflowStepId: uuid("workflow_step_id").notNull().references(() => workflowSteps.id, { onDelete: "cascade" }),
  status: workflowRunStatusEnum("status").notNull().default("pending"),
  result: jsonb("result").$type<Record<string, unknown>>(),
  errorMessage: text("error_message"),
  startedAt: timestamp("started_at", { withTimezone: true }),
  finishedAt: timestamp("finished_at", { withTimezone: true }),
});

export const kpiDefinitions = pgTable(
  "kpi_definitions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    slug: text("slug").notNull(),
    name: text("name").notNull(),
    unit: text("unit").notNull(),
    direction: kpiDirectionEnum("direction").notNull(),
    departmentId: uuid("department_id").references(() => departments.id, { onDelete: "set null" }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => [uniqueIndex("kpi_definitions_slug_unique").on(table.slug)],
);

export const kpiValues = pgTable("kpi_values", {
  id: uuid("id").primaryKey().defaultRandom(),
  kpiDefinitionId: uuid("kpi_definition_id").notNull().references(() => kpiDefinitions.id, { onDelete: "cascade" }),
  projectId: uuid("project_id").references(() => projects.id, { onDelete: "cascade" }),
  departmentId: uuid("department_id").references(() => departments.id, { onDelete: "cascade" }),
  value: numeric("value").notNull(),
  periodStart: date("period_start").notNull(),
  periodEnd: date("period_end").notNull(),
  source: text("source").notNull(),
  metadata: jsonb("metadata").$type<Record<string, unknown>>(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const activityLogs = pgTable("activity_logs", {
  id: uuid("id").primaryKey().defaultRandom(),
  actorType: activityActorTypeEnum("actor_type").notNull(),
  actorId: text("actor_id"),
  actorLabel: text("actor_label"),
  projectId: uuid("project_id").references(() => projects.id, { onDelete: "set null" }),
  entityType: text("entity_type").notNull(),
  entityId: text("entity_id"),
  action: text("action").notNull(),
  summary: text("summary").notNull(),
  metadata: jsonb("metadata").$type<Record<string, unknown>>(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});
