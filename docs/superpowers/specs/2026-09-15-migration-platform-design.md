# Stage B: Migration Deployment Platform

## Goal

Enroll and bootstrap a fresh VPS, recreate project resources, deploy immutable releases from exact Git commits, verify health, and roll back without rebuilding before the 30 September 2026 migration.

## Dependency

This design builds on the typed operation envelope and outbound claim protocol in `2026-09-15-operation-foundation-design.md`. Stage B adds operation kinds only through explicit schemas and handlers; it never adds generic shell, systemctl, filesystem, SQL, or SSH execution.

## Domain model

`Project` owns deployable services and project-scoped configuration. `Service` includes project, unique name, executor (`systemd` initially), repository, branch, root directory, runtime recipe, structured install/build configuration, service port, health-check reference, and target server.

`Deployment` records requested commit/ref, resolved exact commit, state, actor, timestamps, active/previous release, failure code, and source deployment for redeploy/rollback. Its states are:

```text
queued -> preparing -> cloning -> building -> releasing -> health_check
       -> activating -> verifying -> succeeded
       -> failed
       -> rolled_back
```

Transitions are controlled by a deployment state service. Every transition appends an immutable `DeploymentEvent` with redacted structured metadata. Failure before activation preserves current. Failure after activation atomically restores the previous symlink, restarts it, verifies it, and ends `rolled_back`; inability to restore ends `failed` with a high-severity audit event.

`Release` identifies an immutable release directory, exact commit, creation deployment, activation timestamps, and retention eligibility. `EnvironmentVariable`, `Volume`, `Domain`, `HealthCheck`, and `DatabaseResource` use UUID external identities and explicit ownership/target relationships.

## Hybrid executor

The executor boundary exposes prepare, build, configure, activate, restart, verify, and rollback behavior through typed context/result objects. `SystemdExecutor` is the only registered implementation. Executor selection rejects unknown values. Future `DockerExecutor` and `ComposeExecutor` can implement the interface without changing deployment state or API contracts.

The Systemd implementation uses fixed executable argument arrays and platform-owned unit templates. Structured runtime recipes are allow-listed:

- Node/Next.js: package-manager selection, `npm ci`, named build script, start mode, and service port.
- Python/Django: virtualenv dependency install, typed migrate/collectstatic flags, fixed gunicorn module, and service port.

Repository URLs, branches, commits, root directories, script names, module names, and ports are independently validated. No recipe field contains shell syntax.

## Releases and activation

The service root is `/srv/digitalafarin/apps/<project>/<service>/`, containing `releases/`, `shared/`, and `current`. Release names use UTC time plus an abbreviated exact commit. Paths are derived from validated slugs and resolved beneath the configured base directory to prevent traversal.

Deployment resolves the requested ref to an exact commit, creates a fresh release, checks out that commit without modifying `current`, installs/builds through the selected recipe, writes execution-only variables, attaches persistent volumes, runs typed pre-deploy tasks, and performs the pre-activation health check when supported. Activation replaces `current` atomically using a temporary symlink and rename, restarts the service, and verifies health. Rollback switches to an existing successful release and never rebuilds.

Five successful inactive releases are retained per service. Failed logs and metadata are bounded by age/size policy. Cleanup operates only inside a service's `releases/` directory and cannot traverse symlinks. It never deletes `shared`, managed volumes, backups, or database data.

## Environment variables and secrets

Variables have `plain` or `secret` type and project, service, or environment scope. Scope precedence is environment over service over project, with duplicate keys rejected within a scope.

Secrets are encrypted at rest with authenticated encryption under a versioned key supplied outside the database. Create/update APIs accept plaintext once and return only metadata plus `has_value`; list/detail APIs cannot decrypt or serialize plaintext. Decryption exists only in the agent execution path for an authorized deployment and is held in memory or a mode-`0600` ephemeral release environment file. Rotation supports decrypt-with-old/encrypt-with-primary.

One centralized redaction service receives known secret values at execution time and also applies pattern-based redaction. Audit events, deployment events, operation results, build logs, exception strings, Admin responses, and MCP output pass through it before persistence or serialization.

## Managed volumes

Volumes live under `/srv/digitalafarin/volumes/<project>/<name>` and store name, server, service, host path, mount path, owner, group, mode, and backup policy. Host paths are platform-derived beneath the base path; callers cannot provide arbitrary host paths. Creation is typed and idempotent, validates Unix identity/mode inputs, creates the directory, and applies ownership/permissions. Releases attach volumes through configured links or service mounts without copying their contents.

The invariant is enforced in cleanup tests: releases are disposable; volumes are persistent and survive deploy, failed deploy, redeploy, rollback, and retention cleanup.

## PostgreSQL resources

`DatabaseResource` records server, project/service ownership, database/user identifiers, encrypted credential material, lifecycle status, and backup metadata. Typed operations support create database, create role, rotate/generated credential, restore a selected platform-managed backup, and inject `DATABASE_URL` into the secure deployment environment.

Identifiers and backup IDs are validated; SQL uses fixed administration routines with parameterized identifiers/values or dedicated PostgreSQL utilities. There is no SQL text field or console. Restore stages into a controlled database, verifies command completion and connectivity, and records only redacted outcomes.

## Bootstrap and readiness

A typed, idempotent bootstrap operation checks supported OS, disk, memory, Git, Python, Node, PostgreSQL, Nginx, systemd, service account permissions, and required base directories. It creates:

- `/srv/digitalafarin/apps`
- `/srv/digitalafarin/volumes`
- `/srv/digitalafarin/backups`

Each check produces a structured readiness item (`ready`, `warning`, `blocked`) visible in API, MCP, and Admin UI. Package installation, if enabled, is allow-listed by supported OS/runtime recipe and never caller-specified.

## Disk guardrail

Deployment creation requires a fresh disk snapshot. At `>=80%`, creation succeeds with a warning event. At `>=90%`, creation is rejected before queueing. Missing/stale disk data blocks deployment conservatively. Cleanup may be suggested but never touches persistent resources.

## GitHub integration

Manual deploy-latest, exact-commit deploy, redeploy, and rollback ship first. Deploy-latest resolves the configured branch once and stores the resulting commit. A later task adds GitHub webhook auto-deploy only after manual flows pass acceptance. Webhooks verify the signature against an encrypted secret, validate repository/branch mapping, deduplicate delivery IDs, and create a normal control-plane operation; GitHub receives no VPS access.

## Domains and SSL

Domains are typed resources bound to a service and port. The agent renders a platform-owned Nginx template into a staging file, runs `nginx -t`, atomically installs it, and performs a fixed reload operation. SSL uses a typed Certbot workflow for the declared domain. Neither API nor UI accepts Nginx text or commands.

## Admin and MCP

The Admin UI adds Projects and project sections for Services, Deployments, Variables, Volumes, Databases, and Domains. Service detail provides Overview, Deployments, Logs, Variables, Volumes, Domains, and Settings. Deployment history shows commit, state, timestamps/duration, redacted logs, active release, Redeploy, and Rollback.

A migration-readiness view presents the ordered workflow from enrollment through DNS cutover, backed by real resource/readiness/deployment states. Secret values are never rendered or included in page props. MCP mirrors operational reads and narrowly scoped mutations; it never returns secret material.

## Migration acceptance fixture

Acceptance runs against a disposable, non-production filesystem/server fixture with controlled fake systemd/PostgreSQL/Nginx boundaries and a real local Git repository. It proves enrollment, bootstrap, project/service creation, plain and secret variables, volume persistence, exact-commit deploy/build, health check, activation, redeploy, rollback without rebuild, database restore orchestration, bounded logs, redaction, and both disk thresholds.

Where the host provides systemd/PostgreSQL/Nginx, separate opt-in integration checks validate fixed command contracts without restarting a production service. Final production validation is non-destructive unless the exact target and operation are explicitly demonstrated safe.

## Verification and delivery

Every subsystem is implemented test-first. Before integration, run Django full tests and migration checks, Agent/MCP full suites, Web tests/lint/production build, secret/arbitrary-execution scans, systemd unit verification, Nginx configuration verification, tunnel doctor, listener checks, and migration fixture acceptance.

After the feature branch passes, merge latest `main` into it and rerun the full suite. Only then push the feature branch, integrate to `main`, deploy final `main`, repeat production-safe verification, and leave a clean working tree. Reports contain commit IDs and pass/fail evidence but no credentials, tokens, passwords, private keys, secret values, or `SECRET_KEY`.
