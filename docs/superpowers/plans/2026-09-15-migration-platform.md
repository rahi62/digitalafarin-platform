# Migration Deployment Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a migration-ready Systemd deployment platform with bootstrap, secrets, volumes, PostgreSQL restore, immutable releases, health checks, rollback, domains, and operational UI/MCP workflows.

**Architecture:** Domain state lives in Django and work is delivered through Stage A typed operations. An executor-neutral deployment orchestrator drives the only active `SystemdExecutor`, whose agent handlers use fixed structured commands and safe filesystem roots.

**Tech Stack:** Django 5/DRF, authenticated encryption, Python agent, systemd/Git/PostgreSQL/Nginx/Certbot typed adapters, MCP Python SDK, Next.js 16/TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-15-migration-platform-design.md`

## Global Constraints

- Keep Agent outbound-only and API/Web/MCP loopback-only.
- No arbitrary shell, SQL, systemctl, filesystem browser, or Nginx text input.
- Releases are disposable; volumes/backups/databases are persistent.
- Secrets can be decrypted only for authorized execution and never returned by API/UI/MCP.
- Warn at disk `>=80%`; reject deployment creation at `>=90%` or when disk telemetry is stale.
- Retain five successful inactive releases and never require rebuild for rollback.

---

### Task 1: Project and service domain

**Files:**
- Modify: `apps/api/control/models.py`
- Create: `apps/api/control/migrations/0007_deployment_domain.py`
- Create: `apps/api/control/deployment_serializers.py`
- Create: `apps/api/control/deployment_views.py`
- Modify: `apps/api/control/control_urls.py`
- Create: `apps/api/control/tests/test_project_service_api.py`

**Interfaces:**
- Produces: UUID-backed `Project`, `Service`, `HealthCheck`, `Deployment`, `Release`, and `DeploymentEvent`; project/service CRUD APIs.

- [ ] Write failing model/API tests for ownership, uniqueness, exact field validation, executor allow-list, runtime recipe schema, and secret-free serialization.
- [ ] Run focused tests and confirm missing-model failures.
- [ ] Add models/migration and strict serializers/views.
- [ ] Re-run focused tests and migration drift check.
- [ ] Commit with `feat: add deployment domain models`.

### Task 2: Encrypted environment variables

**Files:**
- Modify: `apps/api/requirements.txt`
- Modify: `apps/api/control/models.py`
- Create: `apps/api/control/migrations/0008_environment_variables.py`
- Create: `apps/api/control/services/secrets.py`
- Create: `apps/api/control/environment_views.py`
- Modify: `apps/api/control/control_urls.py`
- Create: `apps/api/control/tests/test_environment_variables.py`

**Interfaces:**
- Produces: `encrypt_secret`, execution-only `decrypt_secret`, scope resolver, and metadata-only variable APIs.

- [ ] Write failing tests for authenticated encryption, wrong-key rejection, versioned rotation, scope precedence, write-only secret input, no plaintext reads, and serializer/audit leakage.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement key-ring configuration and encrypted model storage; keep decryption out of serializers/views.
- [ ] Implement scope resolution and create/update/list/delete endpoints.
- [ ] Re-run focused and Django full suites; scan fixtures/output for sentinel secrets.
- [ ] Commit with `feat: add encrypted deployment variables`.

### Task 3: Managed volumes

**Files:**
- Modify: `apps/api/control/models.py`
- Create: `apps/api/control/migrations/0009_volumes.py`
- Create: `apps/api/control/volume_views.py`
- Create: `apps/api/control/tests/test_volumes.py`
- Create: `agent/digitalafarin_agent/volumes.py`
- Create: `agent/tests/test_volumes.py`

**Interfaces:**
- Produces: metadata API and typed idempotent volume create/attach handlers rooted at `/srv/digitalafarin/volumes`.

- [ ] Write failing API/agent tests for derived host paths, traversal rejection, owner/group/mode validation, idempotence, and persistence through release cleanup.
- [ ] Run focused tests and confirm missing behavior.
- [ ] Add model/API and fixed-root agent handler using safe path resolution.
- [ ] Re-run Django and Agent focused suites.
- [ ] Commit with `feat: add persistent managed volumes`.

### Task 4: Bootstrap and readiness

**Files:**
- Create: `apps/api/control/services/readiness.py`
- Create: `apps/api/control/tests/test_bootstrap_api.py`
- Create: `agent/digitalafarin_agent/bootstrap.py`
- Create: `agent/tests/test_bootstrap.py`
- Modify: `agent/digitalafarin_agent/operations.py`

**Interfaces:**
- Produces: `server.bootstrap` typed operation and structured readiness results.

- [ ] Write failing tests for supported OS, resource/tool checks, fixed base directories, permissions, idempotence, and rejection of caller package/command/path fields.
- [ ] Run focused tests and verify missing handler/result failures.
- [ ] Implement fixed check/create actions and readiness aggregation.
- [ ] Re-run focused suites and prove a second bootstrap produces no destructive changes.
- [ ] Commit with `feat: add typed server bootstrap`.

### Task 5: PostgreSQL resource and restore workflow

**Files:**
- Modify: `apps/api/control/models.py`
- Create: `apps/api/control/migrations/0010_database_resources.py`
- Create: `apps/api/control/database_views.py`
- Create: `apps/api/control/tests/test_database_resources.py`
- Create: `agent/digitalafarin_agent/postgres.py`
- Create: `agent/tests/test_postgres.py`

**Interfaces:**
- Produces: metadata-only `DatabaseResource` API and typed create/restore/connectivity handlers that return a secure `DATABASE_URL` injection reference.

- [ ] Write failing tests for identifier/backup validation, generated encrypted credential, fixed argv, parameterized administration boundary, restore staging, redacted failures, and absence of SQL text input.
- [ ] Run focused tests and confirm missing behavior.
- [ ] Implement model/API and typed PostgreSQL adapter.
- [ ] Re-run focused suites and sentinel-secret scans.
- [ ] Commit with `feat: add secure database restore resources`.

### Task 6: Release engine and SystemdExecutor

**Files:**
- Create: `agent/digitalafarin_agent/executors/base.py`
- Create: `agent/digitalafarin_agent/executors/systemd.py`
- Create: `agent/digitalafarin_agent/releases.py`
- Create: `agent/tests/test_release_engine.py`
- Create: `agent/tests/test_systemd_executor.py`
- Create: `apps/api/control/services/deployments.py`
- Create: `apps/api/control/tests/test_deployment_state.py`

**Interfaces:**
- Produces: `DeploymentExecutor` protocol, `SystemdExecutor`, release preparation/atomic switch/rollback functions, and audited deployment transition service.

- [ ] Write failing tests for every legal/illegal deployment transition and immutable event creation.
- [ ] Write failing filesystem tests using a real local Git fixture for exact commit checkout, pre-current build, atomic symlink activation, rollback without rebuild, and release-root traversal defense.
- [ ] Write failing recipe tests for exact Node and Django argv and rejection of shell metacharacter-bearing structured fields.
- [ ] Implement minimal state service, executor interface/registry, recipes, release filesystem engine, and Systemd executor.
- [ ] Re-run focused suites and source security scans.
- [ ] Commit with `feat: add immutable systemd release engine`.

### Task 7: Health checks, disk guardrail, rollback, and retention

**Files:**
- Modify: `apps/api/control/services/deployments.py`
- Create: `apps/api/control/tests/test_deployment_workflow.py`
- Create: `agent/digitalafarin_agent/health.py`
- Create: `agent/tests/test_health_and_retention.py`
- Modify: `agent/digitalafarin_agent/releases.py`

**Interfaces:**
- Produces: end-to-end deployment orchestration, fixed HTTP health check, disk admission decision, and safe five-release retention.

- [ ] Write failing tests for `>=80%` warning, `>=90%`/stale block, pre/post activation health, successful activation, automatic rollback, rollback verification failure, and five-release cleanup preserving persistent roots.
- [ ] Run focused tests and observe missing branches.
- [ ] Implement guardrail, fixed health client, orchestration steps, compensation, and lstat-based retention cleanup.
- [ ] Re-run focused and full Django/Agent suites.
- [ ] Commit with `feat: enforce safe deployment activation and rollback`.

### Task 8: Manual deploy APIs and GitHub webhook

**Files:**
- Modify: `apps/api/control/deployment_views.py`
- Modify: `apps/api/control/control_urls.py`
- Create: `apps/api/control/github_views.py`
- Create: `apps/api/control/models.py`
- Create: `apps/api/control/migrations/0011_github_deliveries.py`
- Create: `apps/api/control/tests/test_deployment_actions.py`
- Create: `apps/api/control/tests/test_github_webhook.py`

**Interfaces:**
- Produces: deploy-latest, exact-commit, redeploy, rollback endpoints and signature-verified deduplicated webhook-to-operation mapping.

- [ ] Write failing tests for exact ref resolution, disk admission, redeploy provenance, rollback release selection, signature verification, repository/branch filtering, delivery deduplication, and no direct agent access.
- [ ] Run focused tests and verify missing endpoint failures.
- [ ] Implement actions using the normal operation/deployment services and encrypted webhook secret.
- [ ] Re-run focused and Django full suites.
- [ ] Commit with `feat: add deploy actions and github webhook`.

### Task 9: Domains and SSL typed workflow

**Files:**
- Modify: `apps/api/control/models.py`
- Create: `apps/api/control/migrations/0012_domains.py`
- Create: `apps/api/control/domain_views.py`
- Create: `apps/api/control/tests/test_domains.py`
- Create: `agent/digitalafarin_agent/domains.py`
- Create: `agent/tests/test_domains.py`

**Interfaces:**
- Produces: `Domain` API and typed render/validate/install/reload/Certbot handlers.

- [ ] Write failing tests for hostname/port ownership, fixed template output, staging validation before atomic install, fixed Nginx/Certbot argv, and rejection of configuration text/flags.
- [ ] Run focused tests and confirm missing behavior.
- [ ] Implement domain model/API and agent adapter.
- [ ] Re-run focused suites and Nginx fixture verification.
- [ ] Commit with `feat: add typed domain and ssl workflow`.

### Task 10: Migration MCP and Admin UI

**Files:**
- Modify: `mcp/digitalafarin_vps_mcp/control_plane.py`
- Modify: `mcp/digitalafarin_vps_mcp/server.py`
- Create: `mcp/tests/test_deployment_tools.py`
- Modify: `apps/web/lib/control-plane.ts`
- Create: `apps/web/lib/deployments.test.ts`
- Create: `apps/web/app/projects/page.tsx`
- Create: `apps/web/app/projects/[projectId]/page.tsx`
- Create: `apps/web/app/services/[serviceId]/page.tsx`
- Create: `apps/web/app/deployments/[deploymentId]/page.tsx`
- Modify: `apps/web/components/SidebarNav.tsx`

**Interfaces:**
- Produces: secret-free operational tools/pages for resources, deployment actions/history/logs, and migration readiness.

- [ ] Write failing MCP tests for narrow resource/deployment operations and sentinel-secret exclusion.
- [ ] Write failing Web client tests for project/service/resource/history/readiness shapes and action routes.
- [ ] Implement MCP client/tools and minimal Admin pages/tabs using server-only credentials.
- [ ] Run MCP and Web full tests, ESLint, and production build.
- [ ] Commit with `feat: expose migration operations in mcp and admin`.

### Task 11: Migration fixture acceptance

**Files:**
- Create: `acceptance/test_migration_readiness.py`
- Create: `acceptance/fixtures/sample-node/package.json`
- Create: `acceptance/fixtures/sample-node/build.mjs`
- Create: `acceptance/README.md`

**Interfaces:**
- Consumes: all preceding tasks.
- Produces: one safe disposable end-to-end proof covering the 18 acceptance requirements.

- [ ] Write the acceptance test with a temporary filesystem, real local Git commits, controlled command adapters, health fixture, persistent-volume sentinel, database-backup fixture, and secret sentinels.
- [ ] Run it before completing fixture integration and confirm it fails at the first missing workflow behavior.
- [ ] Connect production services/adapters to the fixture without test-only production methods.
- [ ] Run acceptance twice to prove bootstrap idempotence and repeatable redeploy/rollback.
- [ ] Commit with `test: add migration readiness acceptance fixture`.

### Task 12: Full verification, integration, deployment, and clean handoff

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Create: `docs/migration-runbook.md`

**Interfaces:**
- Produces: verified feature/main commits, production-safe deployment, and final evidence report.

- [ ] Document bootstrap, encryption-key provisioning without values, project restore sequence, rollback, retention, disk thresholds, and production-safe checks.
- [ ] Run Django full suite/check/migration drift, Agent/MCP suites, Web tests/lint/build, security scans, systemd verification, Nginx verification, tunnel doctor, listener verification, and migration acceptance.
- [ ] Fix failures test-first, rerun the complete matrix, and commit documentation/fixes.
- [ ] Fetch and merge latest `origin/main`; rerun the complete matrix.
- [ ] Push the feature branch, integrate to `main`, push `main`, deploy final `main`, and run only non-destructive production acceptance unless a specific mutation is explicitly safe.
- [ ] Verify both local and deployed working trees are clean and produce a credential-free report of tests, commits, and all 18 readiness checks.
