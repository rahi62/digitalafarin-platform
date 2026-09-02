# DigitalAfarin Agency Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing DigitalAfarin Agency MCP into a PostgreSQL-backed Agency Core with secure REST API, RTL Next.js Control Center, approval/audit primitives, and preserved MCP compatibility.

**Architecture:** Keep the current Node/TypeScript MCP deployment stable on `127.0.0.1:3050`, add PostgreSQL/Drizzle and reusable domain services behind existing MCP tools, then expose `/api/v1` for a separate Next.js admin service on `127.0.0.1:3060`. Nginx serves the RTL panel at `agency.digitalafarin.ir` and proxies only `/api/*` to Agency Core; `/mcp` stays private behind the existing Secure MCP Tunnel.

**Tech Stack:** Node.js >=20, TypeScript, Express, MCP SDK, Zod, PostgreSQL, Drizzle ORM, Argon2id, Next.js, React, Tailwind CSS.

**Spec:** `docs/superpowers/specs/2026-09-02-agency-control-center-design.md`

## Global Constraints

- Existing nine MCP tool names and behavior remain compatible during migration.
- Existing production project/decision/task data must survive JSON -> PostgreSQL migration.
- Backend continues binding to `127.0.0.1:3050`.
- Admin binds to `127.0.0.1:3060`.
- UI is Persian-first and RTL-first (`lang="fa"`, `dir="rtl"`).
- WordPress MCP stays a separate service and must not regress.
- No public proxy for `/mcp`.
- High/critical-risk execution always requires backend-enforced human approval in v1.
- Secrets, private keys, raw session tokens, and production credentials must never be committed or returned by normal APIs.
- Do not introduce client portal, CRM, billing, visual workflow builder, or other v1 non-goals from the spec.

---

## File Map

### Existing backend files kept compatible
- `src/index.ts` — Express process bootstrap and MCP endpoint; compose REST API without changing MCP path.
- `src/server.ts` — MCP registrations; refactor handlers to domain services only after repositories exist.
- `src/config.ts` — add database/auth/admin configuration.
- `src/store.ts` — temporary compatibility facade, then PostgreSQL-backed adapter; do not delete until migration is proven.

### New backend areas
- `src/db/client.ts` — PostgreSQL/Drizzle client.
- `src/db/schema.ts` — normalized Agency schema.
- `src/db/migrate.ts` — migration runner entrypoint.
- `src/domain/*` — business services shared by MCP and REST.
- `src/auth/*` — password hashing, opaque sessions, CSRF, RBAC.
- `src/api/*` — REST routers.
- `src/migration/import-json-store.ts` — idempotent import preserving existing UUIDs/timestamps.
- `src/activity/service.ts` — append-only audit events.
- `drizzle.config.ts` — migration configuration.

### Admin
- `admin/package.json`
- `admin/next.config.ts`
- `admin/app/layout.tsx`
- `admin/app/(auth)/login/page.tsx`
- `admin/app/(dashboard)/layout.tsx`
- `admin/app/(dashboard)/page.tsx`
- `admin/app/(dashboard)/projects/*`
- `admin/app/(dashboard)/tasks/*`
- `admin/app/(dashboard)/departments/*`
- `admin/app/(dashboard)/approvals/*`
- `admin/app/(dashboard)/activity/*`
- `admin/app/(dashboard)/integrations/*`
- `admin/app/(dashboard)/settings/*`
- `admin/components/*`
- `admin/lib/api.ts`
- `admin/lib/types.ts`

### Deployment
- `deploy/digitalafarin-agency-admin.service`
- `deploy/nginx-agency-control-center.conf.example`
- `deploy/install-admin.sh`
- update `deploy/install-server.sh` only where required for DB migration/dependencies.

---

### Task 1: Add PostgreSQL and Drizzle foundation without changing runtime behavior

**Files:**
- Modify: `package.json`
- Modify: `.env.example`
- Modify: `src/config.ts`
- Create: `drizzle.config.ts`
- Create: `src/db/client.ts`
- Create: `src/db/schema.ts`
- Create: `src/db/migrate.ts`
- Create: `src/db/schema.test.ts`

**Interfaces:**
- Produces `db` Drizzle client.
- Produces typed tables for users, roles, permissions, sessions, departments, projects, notes, decisions, tasks, approvals, executions, workflows, KPIs, integrations and activity logs.
- Existing MCP code does not use these tables yet.

- [ ] Add dependencies: `drizzle-orm`, `postgres`, `argon2`; dev dependency `drizzle-kit`; test runner `vitest`.
- [ ] Add scripts: `test`, `db:generate`, `db:migrate`, `db:check`.
- [ ] Add `DATABASE_URL` and auth/session settings to `.env.example` with no real credentials.
- [ ] Write schema tests that assert project slug uniqueness, task status/risk enums, approval/execution status enums and required foreign-key fields compile/import correctly.
- [ ] Run `npm run check` and `npm test`; expected PASS without requiring a live database for schema import tests.
- [ ] Commit: `feat: add Agency PostgreSQL schema foundation`.

### Task 2: Build repository/domain layer and JSON import with data preservation

**Files:**
- Create: `src/domain/projects/repository.ts`
- Create: `src/domain/projects/service.ts`
- Create: `src/domain/tasks/repository.ts`
- Create: `src/domain/tasks/service.ts`
- Create: `src/domain/decisions/service.ts`
- Create: `src/domain/notes/service.ts`
- Create: `src/migration/import-json-store.ts`
- Create: `src/migration/import-json-store.test.ts`
- Modify: `src/store.ts`

**Interfaces:**
- Preserve current public functions: `listProjects`, `getProject`, `upsertProject`, `addNote`, `recordDecision`, `createTask`, `updateTask`.
- Add independent project `slug` field.
- Importer signature: `importJsonStore(sourcePath: string): Promise<ImportReport>`.

- [ ] Write failing importer tests using a temporary JSON fixture containing project, notes, decisions and tasks with known UUIDs/timestamps.
- [ ] Verify rerunning importer does not duplicate records.
- [ ] Implement transaction-based importer preserving IDs and timestamps.
- [ ] Implement database repositories and map normalized rows back into the existing MCP-compatible project shape.
- [ ] Keep JSON implementation available behind explicit `STORE_DRIVER=json|postgres` during rollout; default production is not switched in this task.
- [ ] Run unit tests and TypeScript checks.
- [ ] Commit: `feat: add PostgreSQL repositories and JSON migration`.

### Task 3: Cut existing MCP tools over to PostgreSQL with regression coverage

**Files:**
- Modify: `src/store.ts`
- Modify: `src/server.ts`
- Create: `src/server.test.ts`
- Update: `README.md`

**Interfaces:**
- Existing nine MCP tool names remain unchanged.
- Existing UUID project IDs remain valid.
- `agency_upsert_project` gains optional `slug` while remaining backward-compatible.

- [ ] Write regression tests for all nine tool registrations and core read/write paths.
- [ ] Add slug validation (`^[a-z0-9]+(?:-[a-z0-9]+)*$`) and unique conflict errors.
- [ ] Switch production adapter to PostgreSQL only after importer validation.
- [ ] Run `npm run check`, `npm test`, `npm run build`.
- [ ] On VPS: back up `data/store.json`, run importer, compare project/decision/task counts, then set `STORE_DRIVER=postgres`.
- [ ] Restart only `digitalafarin-agency-mcp`; test `/health`, MCP initialize, tools/list, `agency_get_team`, `agency_list_projects`, `agency_get_project` and one reversible task update.
- [ ] Confirm WordPress MCP and original WordPress tunnel remain active.
- [ ] Commit: `feat: migrate Agency MCP persistence to PostgreSQL`.

### Task 4: Add secure auth/session/RBAC and append-only activity service

**Files:**
- Create: `src/auth/password.ts`
- Create: `src/auth/session.ts`
- Create: `src/auth/middleware.ts`
- Create: `src/auth/permissions.ts`
- Create: `src/auth/csrf.ts`
- Create: `src/auth/auth.test.ts`
- Create: `src/activity/service.ts`
- Create: `src/activity/service.test.ts`
- Create: `src/db/seed.ts`

**Interfaces:**
- `hashPassword(password)` and `verifyPassword(hash,password)` use Argon2id.
- `createSession(userId)` returns raw token once; DB stores only SHA-256 hash.
- `requirePermission(permissionKey)` guards REST endpoints.
- `recordActivity(event)` appends audit record.

- [ ] Test password round-trip and rejection.
- [ ] Test raw session token is not present in persisted session record.
- [ ] Test expired/revoked session rejection.
- [ ] Test RBAC allows `super_admin` and denies missing permissions.
- [ ] Test CSRF + Origin checks reject state-changing cross-origin requests.
- [ ] Seed roles/permissions/departments idempotently.
- [ ] Add CLI/bootstrap command for first super admin using environment-supplied email/password; never expose public registration.
- [ ] Commit: `feat: add Agency authentication and RBAC`.

### Task 5: Add REST API v1 using the same domain services as MCP

**Files:**
- Create: `src/http.ts`
- Create: `src/api/response.ts`
- Create: `src/api/auth.ts`
- Create: `src/api/dashboard.ts`
- Create: `src/api/projects.ts`
- Create: `src/api/tasks.ts`
- Create: `src/api/departments.ts`
- Create: `src/api/approvals.ts`
- Create: `src/api/integrations.ts`
- Create: `src/api/activity.ts`
- Create: `src/api/kpis.ts`
- Create: `src/api/api.test.ts`
- Modify: `src/index.ts`

**Interfaces:**
- Prefix all admin API routes with `/api/v1`.
- JSON envelope: `{ "data": ..., "error": null }` or `{ "data": null, "error": { "code": string, "message": string } }`.

- [ ] Test unauthenticated protected routes return 401.
- [ ] Test missing permission returns 403.
- [ ] Test project/task mutation writes activity records.
- [ ] Implement auth routes `/auth/login`, `/auth/logout`, `/auth/me`, `/auth/csrf`.
- [ ] Implement dashboard, projects, tasks, departments, approvals, integrations, activity and KPI endpoints from spec.
- [ ] Add login/mutation rate limits.
- [ ] Ensure `/mcp` behavior and origin logic remain unchanged.
- [ ] Run full regression suite and build.
- [ ] Commit: `feat: expose Agency REST API v1`.

### Task 6: Implement approval and execution state machine

**Files:**
- Create: `src/domain/approvals/policy.ts`
- Create: `src/domain/approvals/service.ts`
- Create: `src/domain/executions/service.ts`
- Create: `src/domain/approvals/service.test.ts`
- Modify: `src/api/approvals.ts`
- Modify: `src/activity/service.ts`

**Interfaces:**
- `evaluateApprovalRequirement({riskLevel, actionType, policy})` is deterministic.
- `approve(id,userId)` and `reject(id,userId,reason)` are transition-safe.
- High/critical actions cannot enter queued execution without approved record.

- [ ] Test low-risk allowed policy path.
- [ ] Test high/critical cannot bypass approval.
- [ ] Test approved/rejected approvals cannot be reviewed twice.
- [ ] Test execution transitions queued -> running -> succeeded/failed.
- [ ] Emit audit event on each transition.
- [ ] Commit: `feat: add approval and execution lifecycle`.

### Task 7: Seed Department model and SEO Operating System v1

**Files:**
- Modify: `src/db/seed.ts`
- Create: `src/domain/departments/seed-data.ts`
- Create: `src/domain/workflows/seo.ts`
- Create: `src/domain/departments/seed.test.ts`

**Interfaces:**
- Seed five departments from spec.
- SEO department contains role/capability definitions and initial workflow.
- Re-running seed is idempotent.

- [ ] Test seed counts and unique slugs.
- [ ] Seed SEO roles: Director, Strategist, Data Analyst, Content Strategist, SEO Editor, Internal Linking, Digital PR, Technical SEO, Automation Engineer, SEO QA, Project Manager, CRO/SEO UX.
- [ ] Seed SEO workflow `Measure -> Diagnose -> Prioritize -> Plan -> Implement -> QA -> Validate -> Measure -> Learn -> Refresh`.
- [ ] Seed baseline SEO KPI definitions without ingesting external data yet.
- [ ] Commit: `feat: seed Agency departments and SEO operating system`.

### Task 8: Scaffold RTL Next.js admin and authentication shell

**Files:**
- Create all `admin/` foundation files listed in File Map.
- Create: `admin/components/app-sidebar.tsx`
- Create: `admin/components/topbar.tsx`
- Create: `admin/components/ltr-text.tsx`
- Create: `admin/lib/api.ts`
- Create: `admin/app/globals.css`

**Interfaces:**
- Browser talks only to same-origin `/api/v1`.
- Root layout uses `lang="fa" dir="rtl"`.
- Technical identifiers render with reusable LTR component.

- [ ] Create Next.js/TypeScript/Tailwind app under `admin/` without changing backend build scripts.
- [ ] Add RTL root layout and right-hand desktop sidebar.
- [ ] Use logical CSS properties; add lint/search check preventing new layout-critical `margin-left/right`, `padding-left/right`, `left/right` usage except documented LTR islands.
- [ ] Implement login page with CSRF bootstrap + cookie session flow.
- [ ] Add authenticated dashboard shell and responsive mobile navigation.
- [ ] Run admin typecheck/build.
- [ ] Commit: `feat: add RTL Agency admin shell`.

### Task 9: Build operational admin pages

**Files:**
- Create/modify dashboard, projects, tasks, departments, approvals, activity and integrations pages/components under `admin/`.

**Interfaces:**
- All data comes from `/api/v1`; no direct DB access from Next.js.

- [ ] Dashboard: active projects, critical tasks, blocked tasks, pending approvals, priorities, recent activity.
- [ ] Projects list/detail with tabs Overview, Tasks, Decisions, Notes, KPIs, Team, Integrations, Activity.
- [ ] Tasks global backlog with filters for project, department, owner, priority, status, executor and risk.
- [ ] Departments overview/detail, starting with SEO.
- [ ] Approvals queue/detail with risk, diff preview, reason and Approve/Reject.
- [ ] Activity append-only list with filters.
- [ ] Integrations health list; no secrets rendered.
- [ ] Settings users/roles read UI; mutation UI may remain super-admin-only.
- [ ] Test RTL desktop and mobile layouts plus key interaction states.
- [ ] Commit: `feat: build Agency operational control center`.

### Task 10: Deploy admin service and same-origin Nginx routing

**Files:**
- Create: `deploy/digitalafarin-agency-admin.service`
- Create: `deploy/install-admin.sh`
- Create: `deploy/nginx-agency-control-center.conf.example`
- Update: `README.md`

**Interfaces:**
- Admin: `127.0.0.1:3060`.
- Public: `https://agency.digitalafarin.ir`.
- `/api/` proxies to backend `127.0.0.1:3050`.
- `/mcp` is not exposed by this vhost.

- [ ] Install/build admin as `deploy` user.
- [ ] Configure systemd hardening and restart policy.
- [ ] Configure Nginx same-origin routes and TLS.
- [ ] Verify direct public request to `/mcp` is not routed to Agency MCP.
- [ ] Verify login, dashboard and authenticated project/task updates.
- [ ] Verify ChatGPT MCP tools still work through Secure MCP Tunnel.
- [ ] Verify WordPress MCP, agent and original WordPress tunnel remain healthy.
- [ ] Commit: `chore: add Agency Control Center deployment`.

### Task 11: Register WordPress MCP as first external executor safely

**Files:**
- Create: `src/integrations/wordpress/client.ts`
- Create: `src/integrations/wordpress/health.ts`
- Create: `src/integrations/wordpress/client.test.ts`
- Modify: `src/domain/integrations/*`
- Modify: `src/api/integrations.ts`

**Interfaces:**
- Agency Core talks to the existing WordPress MCP using its localhost endpoint; do not modify WordPress MCP service code.
- v1 milestone begins read/health-only; mutations are enabled only after approval-policy tests pass.

- [ ] Add WordPress integration registry entry without committing credentials.
- [ ] Implement health/read discovery first.
- [ ] Show WordPress connection state in Admin Integrations.
- [ ] Add one low-risk read workflow end-to-end.
- [ ] Only then add approved mutation execution with high-risk safeguards.
- [ ] Verify existing ChatGPT WordPress Connector behavior is unchanged.
- [ ] Commit: `feat: connect Agency Core to WordPress MCP executor`.

### Task 12: Production acceptance and recovery drill

**Files:**
- Update: `README.md`
- Create: `docs/operations/agency-control-center-runbook.md`

**Interfaces:**
- Runbook covers backup, restore, deploy, rollback, session bootstrap, DB migration and service health.

- [ ] Back up PostgreSQL and retained JSON source.
- [ ] Test restore into a temporary database and verify representative project/task/decision counts.
- [ ] Run MCP discovery/invocation acceptance tests.
- [ ] Run Admin login, project/task bidirectional MCP/UI consistency tests.
- [ ] Run approval bypass negative tests for high-risk actions.
- [ ] Run RTL desktop/mobile acceptance checks.
- [ ] Run WordPress regression checks.
- [ ] Record exact rollback commands in runbook.
- [ ] Commit: `docs: add Agency Control Center operations runbook`.

---

## Execution Order and Release Gates

- **Gate A:** Tasks 1-3. Do not start Admin work until existing MCP works from PostgreSQL in production.
- **Gate B:** Tasks 4-7. Do not expose the admin domain until auth/RBAC/CSRF/approval foundations are green.
- **Gate C:** Tasks 8-10. Ship internal Control Center.
- **Gate D:** Task 11. Integrations become executable only after core operational UI is stable.
- **Gate E:** Task 12. Production recovery and acceptance.

## Self-Review

- Spec coverage: PostgreSQL migration, existing MCP compatibility, auth/RBAC, REST, departments, SEO, approvals/executions, RTL admin, integrations, deployment and recovery are each assigned to a task.
- No client portal/CRM/billing/workflow-builder work is included.
- Existing WordPress MCP remains isolated.
- Type/status names match the design spec.
- Migration and rollback are explicit release gates rather than implicit deployment steps.
