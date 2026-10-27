# DigitalAfarin Agency Control Center — Design Specification

Date: 2026-09-02
Status: Approved direction

## 1. Goal

Evolve `digitalafarin-agency-mcp` from a minimal ChatGPT MCP memory server into the central **DigitalAfarin Agency Core Platform**, while preserving the existing MCP connector and its production tunnel.

The platform will have three responsibilities:

1. **Agency Core** — durable business state, permissions, projects, departments, tasks, decisions, workflows, approvals, integrations, KPI values, and audit history.
2. **MCP Interface** — ChatGPT remains the reasoning engine and uses Agency MCP to read and mutate Agency state.
3. **RTL Control Center** — a separate Next.js admin UI for visibility, control, approval, and operations.

The Control Center is an internal operations product, not a client portal.

## 2. Locked Product Decisions

- UI is **Persian-first and RTL-first**.
- Both internal DigitalAfarin projects and client projects live in the same system.
- v1 is internal-only; no client login/portal.
- Backend remains Node.js/TypeScript and grows into Agency Core.
- PostgreSQL replaces JSON as the source of truth.
- Drizzle ORM is used for database access/migrations.
- Existing JSON store is retained only for migration and emergency export/backup.
- Auth is email/password with secure opaque HttpOnly sessions.
- RBAC is enforced by the backend, not only by the Next.js UI.
- Next.js is a separate admin service, deployed at `agency.digitalafarin.ir`.
- Existing MCP endpoint and Secure MCP Tunnel must remain compatible throughout migration.
- WordPress MCP, GitHub, GSC/GA4 and future services remain independent executors/integrations; they are not merged into Agency Core.
- Sensitive execution goes through an Approval Queue and an auditable execution lifecycle.
- No visual workflow builder, billing, CRM, client portal, chat, calendar, or file manager in v1.

## 3. Current State and Compatibility Constraint

The current backend is a minimal TypeScript/Express MCP service. It stores `projects`, nested `notes`, `decisions`, and `tasks` in one JSON file. The production instance already contains durable DigitalAfarin project state and must not be reset.

The existing production contract must remain valid during the migration:

- `GET /health`
- `POST /mcp`
- current nine MCP tools
- bind to `127.0.0.1:3050`
- existing Secure MCP Tunnel and Connector

The migration must be additive first. PostgreSQL is introduced behind the existing store interface before the JSON implementation is retired.

## 4. High-Level Architecture

```text
                         ChatGPT
                            |
                           MCP
                            |
                  +---------v----------+
                  |    Agency Core     |
                  | Node / TypeScript  |
                  +----+-----------+---+
                       |           |
                 PostgreSQL     REST /api/v1
                                   |
                         +---------v---------+
                         | Next.js Admin UI  |
                         | RTL Control Center|
                         +-------------------+

                  Agency Core Integrations
                    |       |       |
                    v       v       v
               WordPress  GitHub   GSC/GA4
                  MCP      API      APIs
```

The same Agency domain services are used by both MCP handlers and REST controllers. Business rules must not be duplicated between MCP and REST.

## 5. Deployment Topology

Keep the existing backend service and tunnel unchanged in shape:

- `digitalafarin-agency-mcp` -> `127.0.0.1:3050`
- `digitalafarin-agency-mcp-tunnel` -> existing MCP endpoint

Add:

- `digitalafarin-agency-admin` -> Next.js on `127.0.0.1:3060`
- PostgreSQL database: `digitalafarin_agency`
- Nginx vhost: `agency.digitalafarin.ir`

Nginx routing:

```text
https://agency.digitalafarin.ir/api/* -> http://127.0.0.1:3050/api/*
https://agency.digitalafarin.ir/*     -> http://127.0.0.1:3060/*
```

Do **not** publicly proxy `/mcp`; ChatGPT continues to reach MCP through the OpenAI Secure MCP Tunnel.

Using one browser origin for UI and REST minimizes CORS complexity and enables secure SameSite session cookies.

## 6. Repository Shape

Avoid a risky full monorepo rewrite in v1. Preserve current `src/index.ts` and backend deployment paths.

Add focused backend modules under `src/` and a separate admin app under `admin/`:

```text
src/
  index.ts
  server.ts                 # MCP registration only
  http.ts                   # Express REST composition
  config.ts
  db/
    client.ts
    schema.ts
    migrations/
    seed.ts
  auth/
    password.ts
    session.ts
    middleware.ts
    permissions.ts
  domain/
    projects/
    tasks/
    decisions/
    departments/
    approvals/
    workflows/
    integrations/
    kpis/
    activity/
  api/
    auth.ts
    projects.ts
    tasks.ts
    departments.ts
    approvals.ts
    integrations.ts
    activity.ts
    kpis.ts
  migration/
    import-json-store.ts

admin/
  app/
  components/
  lib/
  public/
  package.json

scripts/
  migrate-json-store.ts

docs/
```

After the platform stabilizes, a future refactor may turn this into a workspace/monorepo. That refactor is explicitly out of v1 scope.

## 7. Database Model

### 7.1 Identity and Access

#### users
- id UUID PK
- email CITEXT/normalized unique
- password_hash
- display_name
- status: active | disabled
- created_at
- updated_at
- last_login_at nullable

#### roles
Seeded v1 roles:
- `super_admin`
- `project_manager`
- `seo_manager`
- `developer`
- `viewer`

#### permissions
String permission keys, e.g.:
- `projects.read`
- `projects.write`
- `tasks.read`
- `tasks.write`
- `approvals.review`
- `integrations.manage`
- `users.manage`
- `settings.manage`

#### user_roles / role_permissions
Standard many-to-many mappings.

#### sessions
- id UUID PK
- user_id
- token_hash unique
- expires_at
- created_at
- last_seen_at
- ip_hash nullable
- user_agent nullable

The raw session token is never stored in PostgreSQL.

### 7.2 Organization

#### departments
- id
- slug unique
- name
- mission
- status
- lead_user_id nullable
- created_at
- updated_at

Seed departments:
- SEO
- Product Engineering
- AI & Automation
- Sales & Client Success
- Operations

#### department_roles
Defines operational/virtual roles such as SEO Director, SEO Strategist, Technical SEO, SEO QA, etc.

#### department_members
Maps human users to departments and optional department roles.

### 7.3 Projects

#### projects
- id UUID PK
- name
- slug unique
- type: internal | client
- status: active | paused | archived
- health: healthy | attention | at_risk | critical
- priority: low | medium | high | critical
- summary nullable
- goals JSONB string[]
- stack JSONB string[]
- links JSONB object
- owner_id nullable
- primary_department_id nullable
- start_date nullable
- target_date nullable
- created_at
- updated_at

#### project_members
- project_id
- user_id
- project_role nullable

### 7.4 Decisions and Notes

#### decisions
- id
- project_id
- title
- decision
- rationale nullable
- created_by nullable
- created_at

#### notes
- id
- project_id
- text
- created_by nullable
- created_at

### 7.5 Tasks

#### tasks
- id UUID PK
- project_id
- department_id nullable
- title
- description nullable
- status: todo | doing | done | blocked
- priority: low | medium | high | critical
- risk_level: low | medium | high | critical
- owner_id nullable
- owner_label nullable (compatibility for virtual/specialist owners)
- executor_type: manual | wordpress_mcp | github | automation | other
- integration_connection_id nullable
- approval_required boolean
- expected_impact nullable
- effort nullable
- due_date nullable
- created_by nullable
- created_at
- updated_at
- completed_at nullable

The `owner_label` field preserves the current ability to assign tasks to virtual specialists such as `SEO Lead`, while `owner_id` is used for actual human users.

### 7.6 Approvals and Executions

#### approvals
- id
- project_id
- task_id nullable
- action_type
- integration_connection_id nullable
- risk_level
- status: pending | approved | rejected | expired | cancelled
- requested_by nullable
- requested_at
- reviewed_by nullable
- reviewed_at nullable
- reason nullable
- payload JSONB
- diff_preview JSONB nullable

#### executions
- id
- approval_id nullable
- task_id nullable
- integration_connection_id nullable
- executor_type
- status: queued | running | succeeded | failed | cancelled
- request_payload JSONB
- result_payload JSONB nullable
- error_message nullable
- retry_count
- started_at nullable
- finished_at nullable
- created_at

Approval and Execution are separate records. Approval answers **may this action run?**; Execution records **what actually happened?**

### 7.7 Workflows

v1 uses data-driven workflow templates, not a visual builder.

#### workflows
- id
- department_id nullable
- slug unique
- name
- description nullable
- status: draft | active | archived

#### workflow_steps
- id
- workflow_id
- position
- name
- step_type: manual | analysis | approval | execution | qa
- config JSONB

#### workflow_runs
- id
- workflow_id
- project_id
- status
- current_step
- started_at
- finished_at nullable

#### workflow_step_runs
Records outcome and timestamps per step.

Initial SEO workflow template:

`Measure -> Diagnose -> Prioritize -> Plan -> Implement -> QA -> Validate -> Measure -> Learn -> Refresh`

### 7.8 KPIs

#### kpi_definitions
- id
- slug unique
- name
- unit
- direction: increase | decrease | target
- department_id nullable

#### kpi_values
- id
- kpi_definition_id
- project_id nullable
- department_id nullable
- value numeric
- period_start
- period_end
- source
- metadata JSONB

### 7.9 Integrations

#### integration_connections
- id
- slug unique
- name
- type: wordpress_mcp | github | gsc | ga4 | other
- status: connected | degraded | disconnected | disabled
- endpoint nullable
- config JSONB (non-secret metadata only)
- encrypted_secret_ref nullable
- last_health_at nullable
- last_success_at nullable
- created_at
- updated_at

Secrets must not be returned through normal REST list/detail APIs or activity logs.

### 7.10 Activity Log

#### activity_logs
Append-only.

- id
- actor_type: user | chatgpt | system | integration
- actor_id/label nullable
- project_id nullable
- entity_type
- entity_id nullable
- action
- summary
- metadata JSONB
- created_at

Examples:
- task.created
- task.completed
- decision.recorded
- approval.requested
- approval.approved
- execution.succeeded
- execution.failed
- auth.login

## 8. JSON -> PostgreSQL Migration

The existing production JSON data is valuable and must be preserved.

Migration sequence:

1. Deploy PostgreSQL schema without changing MCP reads/writes.
2. Back up `data/store.json` with timestamp + SHA256.
3. Run an idempotent import script that preserves existing UUIDs and timestamps.
4. Validate counts and representative project/task/decision records.
5. Switch the store interface to PostgreSQL.
6. Restart MCP and run all existing discovery/invocation regression tests.
7. Keep the original JSON backup read-only.

The importer uses conflict-safe inserts by primary key and does not duplicate records when rerun.

A failed import must not modify or delete the source JSON file.

## 9. Auth and Security

### Login

- email + password
- Argon2id password hashing
- opaque random session token (>= 256 bits)
- only SHA-256 session token hash stored in DB
- HttpOnly cookie
- Secure in production
- SameSite=Lax
- explicit expiry and server-side revocation

### CSRF

Because the browser uses cookie auth, all state-changing REST requests must pass:

- same-origin `Origin` validation
- CSRF token validation

### RBAC

REST handlers call a shared backend authorization service. UI visibility is convenience only; it is never the security boundary.

`super_admin` receives all v1 permissions. The first production user is seeded manually through a CLI command or one-time environment-protected bootstrap, never through a public registration page.

### Rate limiting

Apply rate limits to login and mutation endpoints. Lockout must be time-bound; do not permanently lock a user due to network abuse.

### Audit

Authentication events, permission-relevant changes, approvals and executions are audited. Passwords, raw sessions, integration credentials and sensitive request headers are never logged.

## 10. REST API v1

Prefix: `/api/v1`

### Auth
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `GET /auth/csrf`

### Dashboard
- `GET /dashboard/summary`

### Projects
- `GET /projects`
- `POST /projects`
- `GET /projects/:id`
- `PATCH /projects/:id`
- `GET /projects/:id/tasks`
- `GET /projects/:id/decisions`
- `GET /projects/:id/notes`
- `GET /projects/:id/activity`

### Tasks
- `GET /tasks`
- `POST /tasks`
- `GET /tasks/:id`
- `PATCH /tasks/:id`

### Departments
- `GET /departments`
- `GET /departments/:id`
- `GET /departments/:id/tasks`
- `GET /departments/:id/workflows`

### Approvals
- `GET /approvals`
- `GET /approvals/:id`
- `POST /approvals/:id/approve`
- `POST /approvals/:id/reject`

### Integrations
- `GET /integrations`
- `GET /integrations/:id`
- `POST /integrations/:id/health-check`

### Activity
- `GET /activity`

### KPI
- `GET /kpis`
- `POST /kpis/values`

Responses use a consistent envelope and machine-readable error codes.

## 11. MCP Compatibility and Expansion

The current nine tools continue to work with the same external names.

They are refactored to call domain services backed by PostgreSQL rather than JSON.

Future MCP tools may include:

- `agency_list_departments`
- `agency_get_department`
- `agency_list_approvals`
- `agency_request_approval`
- `agency_get_dashboard`
- `agency_record_kpi`

Do not add new tools until PostgreSQL migration and existing-tool regression tests are green.

## 12. Approval Policy

Default policy:

### Low risk
May run automatically when the integration policy allows it.
Examples: read-only analysis, GSC snapshots, internal link suggestions, report generation.

### Medium risk
Can be auto-approved only by an explicit project/integration policy. Otherwise requires review.

### High/Critical risk
Always requires human approval in v1.
Examples:
- redirect creation/removal
- canonical changes
- noindex/index changes
- delete/unpublish
- mass publishing
- money-page replacement
- production deploy
- DNS/server changes

The backend, not ChatGPT, enforces this policy.

## 13. Execution Lifecycle

```text
Task / Workflow Step
       |
       v
Execution Proposal
       |
       +-- policy permits -> queued
       |
       +-- approval required -> Approval(pending)
                                  |
                      +-----------+-----------+
                      |                       |
                   approved                rejected
                      |                       |
                      v                       v
                    queued                  stop
                      |
                   running
                      |
             +--------+--------+
             |                 |
          succeeded           failed
```

Every transition emits an activity log event.

Retries create/update execution attempts without silently changing the original approval decision.

## 14. Integration Strategy

### WordPress MCP

Remain a separate service. Agency Core may later invoke it using a local MCP client pointed to the existing localhost MCP endpoint. v1 first registers it and exposes health/status before enabling mutation execution.

### GitHub

Registry/status first. Direct execution requires explicit credential design and is not required for the first UI milestone.

### GSC / GA4

Registry and data model first. Their KPI ingestion can be added after the Control Center and PostgreSQL migration are stable.

This phased approach prevents integration work from blocking the core admin platform.

## 15. RTL Admin UX

Root document:

```html
<html lang="fa" dir="rtl">
```

Use CSS logical properties (`margin-inline`, `padding-inline`, `inset-inline`) instead of left/right-specific layout rules.

### Navigation

Sidebar is on the right in Persian:

- داشبورد
- پروژه‌ها
- وظایف
- دپارتمان‌ها
- تأییدها
- فعالیت‌ها
- اتصال‌ها
- تنظیمات

### LTR islands

Use `dir="ltr"` for URLs, UUIDs, commit SHAs, branches, API endpoints, code, and technical numeric strings.

### Visual priority

The UI answers in order:

1. What needs attention now?
2. What is blocked?
3. What awaits my approval?
4. Who owns the work?
5. What changed recently?

Avoid decorative charts that do not support an operational decision.

## 16. Admin Pages v1

### Dashboard
Cards:
- active projects
- P0/critical tasks
- blocked tasks
- pending approvals

Sections:
- today priorities
- approval queue
- project health
- department workload
- recent activity
- upcoming deadlines

### Projects
List with status/health/owner/department/task counts.

Project detail tabs:
- Overview
- Tasks
- Decisions
- Notes
- KPIs
- Team
- Integrations
- Activity

### Tasks
Global backlog with filters for project, department, owner, priority, status, executor, risk.

### Departments
Department overview, mission, roles, members, active projects, workflows, KPIs, task backlog.

### Approvals
Action, project, task, executor, risk, requester, diff/preview, reason, Approve/Reject.

### Activity
Append-only operational history with filters.

### Integrations
Connection health/status/scope/last success. Secrets are never shown.

### Settings
Users, roles, permissions, project access, department access, policies.

## 17. SEO Department Seed

The first real department is SEO.

Operational structure:

- SEO Director
- Strategy & Data
  - SEO Strategist / Topical Authority
  - SEO Data Analyst
- Content & Authority
  - Content Strategist
  - SEO Editor
  - Internal Linking Specialist
  - Digital PR / Off-page
- Technical & Automation
  - Technical SEO
  - SEO Automation Engineer
  - SEO QA
- Delivery & Growth
  - SEO Project Manager
  - CRO / SEO UX

These are capabilities/roles, not necessarily one human employee per role.

The system supports both human assignments and virtual specialist ownership.

## 18. Non-Goals v1

Explicitly excluded:

- client portal
- public registration
- invoicing/accounting
- full CRM
- internal chat
- calendar
- standalone file manager
- visual workflow builder
- autonomous high-risk production execution
- replacing WordPress MCP with Agency code
- rewriting the repository into a workspace monorepo

## 19. Delivery Phases

### Phase 1 — Persistence Foundation
PostgreSQL, Drizzle, schema, migrations, JSON import, domain repositories, existing MCP regression.

### Phase 2 — Identity and REST
Auth, sessions, RBAC, CSRF, activity log, REST API.

### Phase 3 — RTL Control Center
Next.js admin shell, login, Dashboard, Projects, Tasks, Decisions/Notes, Departments.

### Phase 4 — Approval Operations
Approval Queue, execution records, policies, audit views.

### Phase 5 — Integration Control
WordPress MCP registry + health, then carefully-scoped executor integration.

### Phase 6 — SEO Operating System
Seed SEO roles/workflow/KPIs and connect real SEO project operations.

Each phase must leave the production MCP connector usable.

## 20. Acceptance Criteria

The first complete v1 is accepted when:

1. Existing DigitalAfarin project, decisions and tasks survive JSON -> PostgreSQL migration.
2. Existing nine MCP tools continue to pass discovery and invocation tests through the current ChatGPT connector.
3. Admin can log in at `agency.digitalafarin.ir` with secure session auth.
4. UI is genuinely RTL-first on desktop and mobile.
5. Projects, tasks, decisions, notes and departments are visible from the panel.
6. Task status/priority/owner changes made in the panel are visible to ChatGPT through MCP and vice versa.
7. High-risk actions cannot execute without a backend-enforced approval.
8. Approval and execution events appear in the append-only Activity log.
9. WordPress MCP remains an independent healthy service and existing WordPress workflows are not regressed.
10. No credential, session token, private key or production secret is committed to Git or exposed by the API/UI.
