# SDD ledger — plan: docs/superpowers/plans/2026-09-30-vps-deployment-readiness.md

Base: 46f477c. Branch: feat/vps-deployment-platform. User authorized implementation and separate local commits per stage; no push or production deployment.

Ruling: Work in the current checkout on a feature branch — the user's original specification requests this checkout; existing dependencies and unrelated work are preserved.
Ruling: Keep a tracked ledger alongside the roadmap — the roadmap uses Persian phase headings rather than the task extraction script's format; explicit evidence below survives compaction.
Pre-flight: Phase 1 completion/progress must serve provisioning (2) and resource results (4); use one authenticated transactional completion boundary.
Pre-flight: Phase 2 source resolution must preserve existing trusted-local deployments and allow later per-repository credentials (6).
Pre-flight: Runtime configuration snapshots (3) must be shared by fresh provisioning, redeploy and rollback, including Django (5).

## Phase 0 — complete

Baseline previously reproduced: API 97 pass, web 27 pass, lint/build pass; Linux Agent 197 pass / 1 fail (local-source contract fixture).
RED: retention test retained 7 instead of 5; existing source fixture failed as expected.
GREEN: Linux Agent full suite 200 passed (34.55s). Existing source rejection tests preserved, ownership assertions retained. CI added with PostgreSQL, Linux privileged fixtures, web and existing MCP contracts. CI itself has not run remotely (no push).

## Phase 1 — operation foundation implemented; host reconciliation remains a release gate

RED: invalid claim mutated Deployment; duplicate completion and invalid result raised unhandled domain errors (9 targeted API tests: 1 failure, 2 errors).
GREEN: API 101 pass; Agent 205 pass; web 27 pass, lint/build pass; Django check and migration drift pass.
Implemented atomic authenticated completion, replay without duplicate domain events, one claimed/running operation per server, progress with renewable running lease, independent heartbeat/worker, and durable completion outbox. UI shows reported stages and refreshes active operations.
Ruling: Do not automatically rerun an interrupted mutation — the durable journal reports execution_interrupted; a missing journal leaves the running operation blocked for reconciliation. Automatic replay without host proof could restart a live workload twice. Provisioning's host journal must provide that proof in Phase 2.
Outstanding verification: actual PostgreSQL concurrency and VM restart/fencing tests; CI configured, not yet executed remotely.

## Phase 2 — initial managed Next.js provisioning implemented

The project-scoped API accepts a validated public Git repository and creates a pending service, deployment, provisioning record, and typed asynchronous operation in one transaction. The Agent resolves an exact commit, builds an immutable release, installs a fixed systemd unit, checks health, and persists the result. Retries, redeploy, rollback, and best-effort release retention are wired through the same managed binding. The Railway-style project UI now opens a dedicated new-service form and redirects to the service detail page; Migration remains an Advanced workflow.

Verification: Agent 225 passed (Linux root fixture), API 110 passed, web 33 passed, MCP 27 passed, Django system check and migration drift check clean, web lint/build passed, `git diff --check` clean. No VPS smoke test or PostgreSQL concurrency/restart acceptance test was run. The Linux acceptance suite needs a test environment with both Django and Linux Agent dependencies; the available Windows Django environment cannot import `pwd`, while the Linux Agent environment lacks Django.

Remaining Phase 2 release gate: exercise an actual fresh VPS provisioning/deploy/rollback with systemd sandbox, public Git repository, and health endpoint; verify host reconciliation after an interrupted privileged operation.

## Remaining

- Phase 1: operations and recovery
- Phase 2: provisioning and creation UI
- Phase 3: runtime environment and storage
- Phase 4: networking and databases
- Phase 5: Django
- Phase 6: repository credentials and autodeploy
- Phase 7: VPS operations and backup
- Phase 8: end-to-end validation and release package
