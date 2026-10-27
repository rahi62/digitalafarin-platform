CREATE EXTENSION IF NOT EXISTS "pgcrypto";
--> statement-breakpoint
CREATE TYPE "public"."user_status" AS ENUM('active', 'disabled');
--> statement-breakpoint
CREATE TYPE "public"."department_status" AS ENUM('active', 'paused', 'archived');
--> statement-breakpoint
CREATE TYPE "public"."project_type" AS ENUM('internal', 'client');
--> statement-breakpoint
CREATE TYPE "public"."project_status" AS ENUM('active', 'paused', 'archived');
--> statement-breakpoint
CREATE TYPE "public"."project_health" AS ENUM('healthy', 'attention', 'at_risk', 'critical');
--> statement-breakpoint
CREATE TYPE "public"."priority" AS ENUM('low', 'medium', 'high', 'critical');
--> statement-breakpoint
CREATE TYPE "public"."task_status" AS ENUM('todo', 'doing', 'done', 'blocked');
--> statement-breakpoint
CREATE TYPE "public"."risk_level" AS ENUM('low', 'medium', 'high', 'critical');
--> statement-breakpoint
CREATE TYPE "public"."executor_type" AS ENUM('manual', 'wordpress_mcp', 'github', 'automation', 'other');
--> statement-breakpoint
CREATE TYPE "public"."approval_status" AS ENUM('pending', 'approved', 'rejected', 'expired', 'cancelled');
--> statement-breakpoint
CREATE TYPE "public"."execution_status" AS ENUM('queued', 'running', 'succeeded', 'failed', 'cancelled');
--> statement-breakpoint
CREATE TYPE "public"."workflow_status" AS ENUM('draft', 'active', 'archived');
--> statement-breakpoint
CREATE TYPE "public"."workflow_step_type" AS ENUM('manual', 'analysis', 'approval', 'execution', 'qa');
--> statement-breakpoint
CREATE TYPE "public"."workflow_run_status" AS ENUM('pending', 'running', 'succeeded', 'failed', 'cancelled');
--> statement-breakpoint
CREATE TYPE "public"."integration_type" AS ENUM('wordpress_mcp', 'github', 'gsc', 'ga4', 'other');
--> statement-breakpoint
CREATE TYPE "public"."integration_status" AS ENUM('connected', 'degraded', 'disconnected', 'disabled');
--> statement-breakpoint
CREATE TYPE "public"."kpi_direction" AS ENUM('increase', 'decrease', 'target');
--> statement-breakpoint
CREATE TYPE "public"."activity_actor_type" AS ENUM('user', 'chatgpt', 'system', 'integration');
--> statement-breakpoint
CREATE TABLE "users" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "email" text NOT NULL,
  "password_hash" text NOT NULL,
  "display_name" text NOT NULL,
  "status" "user_status" DEFAULT 'active' NOT NULL,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
  "last_login_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "roles" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "slug" text NOT NULL,
  "name" text NOT NULL,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "permissions" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "key" text NOT NULL,
  "description" text,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "user_roles" (
  "user_id" uuid NOT NULL,
  "role_id" uuid NOT NULL,
  CONSTRAINT "user_roles_user_id_role_id_pk" PRIMARY KEY("user_id", "role_id")
);
--> statement-breakpoint
CREATE TABLE "role_permissions" (
  "role_id" uuid NOT NULL,
  "permission_id" uuid NOT NULL,
  CONSTRAINT "role_permissions_role_id_permission_id_pk" PRIMARY KEY("role_id", "permission_id")
);
--> statement-breakpoint
CREATE TABLE "sessions" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "user_id" uuid NOT NULL,
  "token_hash" text NOT NULL,
  "expires_at" timestamp with time zone NOT NULL,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  "last_seen_at" timestamp with time zone DEFAULT now() NOT NULL,
  "ip_hash" text,
  "user_agent" text
);
--> statement-breakpoint
CREATE TABLE "departments" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "slug" text NOT NULL,
  "name" text NOT NULL,
  "mission" text,
  "status" "department_status" DEFAULT 'active' NOT NULL,
  "lead_user_id" uuid,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  "updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "department_roles" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "department_id" uuid NOT NULL,
  "slug" text NOT NULL,
  "name" text NOT NULL,
  "mission" text,
  "responsibilities" jsonb,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  "updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "department_members" (
  "department_id" uuid NOT NULL,
  "user_id" uuid NOT NULL,
  "department_role_id" uuid,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "department_members_department_id_user_id_pk" PRIMARY KEY("department_id", "user_id")
);
--> statement-breakpoint
CREATE TABLE "integration_connections" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "slug" text NOT NULL,
  "name" text NOT NULL,
  "type" "integration_type" NOT NULL,
  "status" "integration_status" DEFAULT 'disconnected' NOT NULL,
  "endpoint" text,
  "config" jsonb,
  "encrypted_secret_ref" text,
  "last_health_at" timestamp with time zone,
  "last_success_at" timestamp with time zone,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  "updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "projects" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "name" text NOT NULL,
  "slug" text NOT NULL,
  "type" "project_type" DEFAULT 'internal' NOT NULL,
  "status" "project_status" DEFAULT 'active' NOT NULL,
  "health" "project_health" DEFAULT 'healthy' NOT NULL,
  "priority" "priority" DEFAULT 'medium' NOT NULL,
  "summary" text,
  "goals" jsonb NOT NULL,
  "stack" jsonb NOT NULL,
  "links" jsonb NOT NULL,
  "owner_id" uuid,
  "primary_department_id" uuid,
  "start_date" date,
  "target_date" date,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  "updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "project_members" (
  "project_id" uuid NOT NULL,
  "user_id" uuid NOT NULL,
  "project_role" text,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  CONSTRAINT "project_members_project_id_user_id_pk" PRIMARY KEY("project_id", "user_id")
);
--> statement-breakpoint
CREATE TABLE "decisions" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "project_id" uuid NOT NULL,
  "title" text NOT NULL,
  "decision" text NOT NULL,
  "rationale" text,
  "created_by" uuid,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "notes" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "project_id" uuid NOT NULL,
  "text" text NOT NULL,
  "created_by" uuid,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "tasks" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "project_id" uuid NOT NULL,
  "department_id" uuid,
  "title" text NOT NULL,
  "description" text,
  "status" "task_status" DEFAULT 'todo' NOT NULL,
  "priority" "priority" DEFAULT 'medium' NOT NULL,
  "risk_level" "risk_level" DEFAULT 'low' NOT NULL,
  "owner_id" uuid,
  "owner_label" text,
  "executor_type" "executor_type" DEFAULT 'manual' NOT NULL,
  "integration_connection_id" uuid,
  "approval_required" boolean DEFAULT false NOT NULL,
  "expected_impact" text,
  "effort" text,
  "due_date" date,
  "created_by" uuid,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
  "completed_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "approvals" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "project_id" uuid NOT NULL,
  "task_id" uuid,
  "action_type" text NOT NULL,
  "integration_connection_id" uuid,
  "risk_level" "risk_level" NOT NULL,
  "status" "approval_status" DEFAULT 'pending' NOT NULL,
  "requested_by" uuid,
  "requested_at" timestamp with time zone DEFAULT now() NOT NULL,
  "reviewed_by" uuid,
  "reviewed_at" timestamp with time zone,
  "reason" text,
  "payload" jsonb NOT NULL,
  "diff_preview" jsonb
);
--> statement-breakpoint
CREATE TABLE "executions" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "approval_id" uuid,
  "task_id" uuid,
  "integration_connection_id" uuid,
  "executor_type" "executor_type" NOT NULL,
  "status" "execution_status" DEFAULT 'queued' NOT NULL,
  "request_payload" jsonb NOT NULL,
  "result_payload" jsonb,
  "error_message" text,
  "retry_count" integer DEFAULT 0 NOT NULL,
  "started_at" timestamp with time zone,
  "finished_at" timestamp with time zone,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "workflows" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "department_id" uuid,
  "slug" text NOT NULL,
  "name" text NOT NULL,
  "description" text,
  "status" "workflow_status" DEFAULT 'draft' NOT NULL,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL,
  "updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "workflow_steps" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "workflow_id" uuid NOT NULL,
  "position" integer NOT NULL,
  "name" text NOT NULL,
  "step_type" "workflow_step_type" NOT NULL,
  "config" jsonb NOT NULL
);
--> statement-breakpoint
CREATE TABLE "workflow_runs" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "workflow_id" uuid NOT NULL,
  "project_id" uuid NOT NULL,
  "status" "workflow_run_status" DEFAULT 'pending' NOT NULL,
  "current_step" integer DEFAULT 0 NOT NULL,
  "started_at" timestamp with time zone DEFAULT now() NOT NULL,
  "finished_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "workflow_step_runs" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "workflow_run_id" uuid NOT NULL,
  "workflow_step_id" uuid NOT NULL,
  "status" "workflow_run_status" DEFAULT 'pending' NOT NULL,
  "result" jsonb,
  "error_message" text,
  "started_at" timestamp with time zone,
  "finished_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "kpi_definitions" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "slug" text NOT NULL,
  "name" text NOT NULL,
  "unit" text NOT NULL,
  "direction" "kpi_direction" NOT NULL,
  "department_id" uuid,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "kpi_values" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "kpi_definition_id" uuid NOT NULL,
  "project_id" uuid,
  "department_id" uuid,
  "value" numeric NOT NULL,
  "period_start" date NOT NULL,
  "period_end" date NOT NULL,
  "source" text NOT NULL,
  "metadata" jsonb,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "activity_logs" (
  "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
  "actor_type" "activity_actor_type" NOT NULL,
  "actor_id" text,
  "actor_label" text,
  "project_id" uuid,
  "entity_type" text NOT NULL,
  "entity_id" text,
  "action" text NOT NULL,
  "summary" text NOT NULL,
  "metadata" jsonb,
  "created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "user_roles" ADD CONSTRAINT "user_roles_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "user_roles" ADD CONSTRAINT "user_roles_role_id_roles_id_fk" FOREIGN KEY ("role_id") REFERENCES "public"."roles"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "role_permissions" ADD CONSTRAINT "role_permissions_role_id_roles_id_fk" FOREIGN KEY ("role_id") REFERENCES "public"."roles"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "role_permissions" ADD CONSTRAINT "role_permissions_permission_id_permissions_id_fk" FOREIGN KEY ("permission_id") REFERENCES "public"."permissions"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "sessions" ADD CONSTRAINT "sessions_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "departments" ADD CONSTRAINT "departments_lead_user_id_users_id_fk" FOREIGN KEY ("lead_user_id") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "department_roles" ADD CONSTRAINT "department_roles_department_id_departments_id_fk" FOREIGN KEY ("department_id") REFERENCES "public"."departments"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "department_members" ADD CONSTRAINT "department_members_department_id_departments_id_fk" FOREIGN KEY ("department_id") REFERENCES "public"."departments"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "department_members" ADD CONSTRAINT "department_members_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "department_members" ADD CONSTRAINT "department_members_department_role_id_department_roles_id_fk" FOREIGN KEY ("department_role_id") REFERENCES "public"."department_roles"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "projects" ADD CONSTRAINT "projects_owner_id_users_id_fk" FOREIGN KEY ("owner_id") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "projects" ADD CONSTRAINT "projects_primary_department_id_departments_id_fk" FOREIGN KEY ("primary_department_id") REFERENCES "public"."departments"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "project_members" ADD CONSTRAINT "project_members_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "project_members" ADD CONSTRAINT "project_members_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "decisions" ADD CONSTRAINT "decisions_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "decisions" ADD CONSTRAINT "decisions_created_by_users_id_fk" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "notes" ADD CONSTRAINT "notes_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "notes" ADD CONSTRAINT "notes_created_by_users_id_fk" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_department_id_departments_id_fk" FOREIGN KEY ("department_id") REFERENCES "public"."departments"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_owner_id_users_id_fk" FOREIGN KEY ("owner_id") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_integration_connection_id_integration_connections_id_fk" FOREIGN KEY ("integration_connection_id") REFERENCES "public"."integration_connections"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_created_by_users_id_fk" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "approvals" ADD CONSTRAINT "approvals_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "approvals" ADD CONSTRAINT "approvals_task_id_tasks_id_fk" FOREIGN KEY ("task_id") REFERENCES "public"."tasks"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "approvals" ADD CONSTRAINT "approvals_integration_connection_id_integration_connections_id_fk" FOREIGN KEY ("integration_connection_id") REFERENCES "public"."integration_connections"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "approvals" ADD CONSTRAINT "approvals_requested_by_users_id_fk" FOREIGN KEY ("requested_by") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "approvals" ADD CONSTRAINT "approvals_reviewed_by_users_id_fk" FOREIGN KEY ("reviewed_by") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "executions" ADD CONSTRAINT "executions_approval_id_approvals_id_fk" FOREIGN KEY ("approval_id") REFERENCES "public"."approvals"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "executions" ADD CONSTRAINT "executions_task_id_tasks_id_fk" FOREIGN KEY ("task_id") REFERENCES "public"."tasks"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "executions" ADD CONSTRAINT "executions_integration_connection_id_integration_connections_id_fk" FOREIGN KEY ("integration_connection_id") REFERENCES "public"."integration_connections"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "workflows" ADD CONSTRAINT "workflows_department_id_departments_id_fk" FOREIGN KEY ("department_id") REFERENCES "public"."departments"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "workflow_steps" ADD CONSTRAINT "workflow_steps_workflow_id_workflows_id_fk" FOREIGN KEY ("workflow_id") REFERENCES "public"."workflows"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "workflow_runs" ADD CONSTRAINT "workflow_runs_workflow_id_workflows_id_fk" FOREIGN KEY ("workflow_id") REFERENCES "public"."workflows"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "workflow_runs" ADD CONSTRAINT "workflow_runs_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "workflow_step_runs" ADD CONSTRAINT "workflow_step_runs_workflow_run_id_workflow_runs_id_fk" FOREIGN KEY ("workflow_run_id") REFERENCES "public"."workflow_runs"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "workflow_step_runs" ADD CONSTRAINT "workflow_step_runs_workflow_step_id_workflow_steps_id_fk" FOREIGN KEY ("workflow_step_id") REFERENCES "public"."workflow_steps"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "kpi_definitions" ADD CONSTRAINT "kpi_definitions_department_id_departments_id_fk" FOREIGN KEY ("department_id") REFERENCES "public"."departments"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "kpi_values" ADD CONSTRAINT "kpi_values_kpi_definition_id_kpi_definitions_id_fk" FOREIGN KEY ("kpi_definition_id") REFERENCES "public"."kpi_definitions"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "kpi_values" ADD CONSTRAINT "kpi_values_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "kpi_values" ADD CONSTRAINT "kpi_values_department_id_departments_id_fk" FOREIGN KEY ("department_id") REFERENCES "public"."departments"("id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "activity_logs" ADD CONSTRAINT "activity_logs_project_id_projects_id_fk" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE set null ON UPDATE no action;
--> statement-breakpoint
CREATE UNIQUE INDEX "users_email_unique" ON "users" USING btree ("email");
--> statement-breakpoint
CREATE UNIQUE INDEX "roles_slug_unique" ON "roles" USING btree ("slug");
--> statement-breakpoint
CREATE UNIQUE INDEX "permissions_key_unique" ON "permissions" USING btree ("key");
--> statement-breakpoint
CREATE UNIQUE INDEX "sessions_token_hash_unique" ON "sessions" USING btree ("token_hash");
--> statement-breakpoint
CREATE UNIQUE INDEX "departments_slug_unique" ON "departments" USING btree ("slug");
--> statement-breakpoint
CREATE UNIQUE INDEX "department_roles_department_slug_unique" ON "department_roles" USING btree ("department_id", "slug");
--> statement-breakpoint
CREATE UNIQUE INDEX "integration_connections_slug_unique" ON "integration_connections" USING btree ("slug");
--> statement-breakpoint
CREATE UNIQUE INDEX "projects_slug_unique" ON "projects" USING btree ("slug");
--> statement-breakpoint
CREATE UNIQUE INDEX "workflows_slug_unique" ON "workflows" USING btree ("slug");
--> statement-breakpoint
CREATE UNIQUE INDEX "workflow_steps_workflow_position_unique" ON "workflow_steps" USING btree ("workflow_id", "position");
--> statement-breakpoint
CREATE UNIQUE INDEX "kpi_definitions_slug_unique" ON "kpi_definitions" USING btree ("slug");
