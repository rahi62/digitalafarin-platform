# Stage B3 — Controlled Takeover Design

**Project:** DigitalAfarin Platform  
**Status:** Design approved in conversation; written-spec review pending  
**Date:** 2026-09-20  
**Scope:** Safe transition of an adopted/configured existing systemd service into DigitalAfarin-managed immutable releases, beginning with `node-nextjs + systemd` and `digitalafarin-platform-web.service`.

## 1. Intent

Stage B3 completes the lifecycle introduced in Stage B2:

```text
adopted
  ↓
configured
  ↓
managed
```

Stage B2 intentionally stopped at `configured · unmanaged`. Stage B3 adds a controlled takeover workflow that can move a configured existing service to `managed` only after:

1. inspecting the existing systemd service,
2. preparing an exact-commit immutable release,
3. persisting a safe snapshot of the pre-takeover service configuration,
4. re-verifying that the source configuration has not changed,
5. activating the managed release with a narrow systemd drop-in,
6. restarting only the exact target service,
7. passing health verification,
8. and preserving a deterministic rollback path.

The first concrete implementation supports only `node-nextjs + systemd`. The architecture remains extensible to additional runtimes later.

## 2. Production baseline

The first production candidate is:

```text
Project:          DigitalAfarin Platform
Service:          platform-web
Unit:             digitalafarin-platform-web.service
Lifecycle:        configured
Runtime:          node-nextjs
Protected:        true
Inventory:        present
Repository:       https://github.com/rahi62/digitalafarin-platform.git
Branch:           main
Root directory:   apps/web
Port:             9751
```

Current effective systemd behavior:

```text
User=deploy
Group=www-data
WorkingDirectory=/opt/digitalafarin-platform/apps/web
EnvironmentFile=/etc/digitalafarin-platform/web.env
ExecStart=/usr/bin/npm start -- --hostname 127.0.0.1 --port 9751
Restart=on-failure
```

The service listens on `127.0.0.1:9751`.

The base unit is `/etc/systemd/system/digitalafarin-platform-web.service`, owned by `root:root`, mode `0644`. The runtime environment file is `/etc/digitalafarin-platform/web.env`, owned by `root:deploy`, mode `0640`.

Stage B3 must preserve the runtime user, group, environment file, executable, arguments, and port. The first takeover changes only the code location used as `WorkingDirectory`.

## 3. Scope and non-goals

### In scope

- a persisted takeover workflow,
- exact-commit admission,
- systemd inspection and stable fingerprinting,
- immutable release preparation under `/srv/digitalafarin/apps`,
- a managed systemd drop-in,
- controlled activation,
- health verification,
- automatic rollback,
- audit events,
- typed API and MCP operations,
- web UI for prepare/activate/observe,
- transition `configured → managed` only after verified success,
- support for a protected service through the dedicated takeover workflow.

### Explicitly out of scope

- arbitrary shell execution,
- caller-supplied filesystem paths,
- caller-supplied unit names during execution,
- weakening the existing protected-service rules,
- `python-django` takeover,
- database cutover,
- Nginx blue/green switching,
- zero-downtime guarantees,
- taking over Oily in the first rollout,
- self-modifying the base systemd unit,
- changing secrets or copying runtime environment values into the database.

## 4. Key architectural decision: two-phase takeover

The current Agent operation protocol persists structured results only when an operation completes. A single operation that both inspects the source service and mutates it would allow the cutover to occur before the Control Plane has durably stored the source snapshot.

Stage B3 therefore uses two phases:

```text
PREPARE
inspect → fingerprint → clone/build → persist prepared result

ACTIVATE
re-inspect → fingerprint compare → install drop-in/current →
restart → health-check → success or rollback
```

This is intentionally safer than a one-shot takeover.

The Control Plane has a durable source snapshot and prepared release metadata before any service mutation occurs.

## 5. Takeover state machine

A new `ServiceTakeover` record owns takeover lifecycle.

```text
queued
  ↓
inspecting
  ↓
preparing
  ↓
prepared
  ├────────────→ canceled
  ↓
activating
  ↓
verifying
  ├────────────→ succeeded
  ├────────────→ rolled_back
  ├────────────→ failed
  └────────────→ rollback_failed
```

Meaning:

- `queued`: prepare operation created but not yet running.
- `inspecting`: Agent is reading the effective source systemd configuration.
- `preparing`: Agent is cloning/building an immutable exact-commit release.
- `prepared`: source snapshot and release metadata are durably stored; no service mutation has occurred.
- `canceled`: prepared takeover abandoned; service remains configured.
- `activating`: `current` and the managed drop-in are being installed and the exact service is being restarted.
- `verifying`: health verification is in progress.
- `succeeded`: health passed and Service is transitioned to `managed`.
- `rolled_back`: activation failed, original service behavior was restored, and original health passed.
- `failed`: prepare failed, or activation stopped before mutation.
- `rollback_failed`: activation failed and original service health could not be re-established automatically.

`Service.lifecycle_state` remains `configured` for every state except successful takeover. It changes to `managed` only in the final success transaction.

## 6. Data model

### 6.1 ServiceTakeover

Add a new model with at least:

```text
public_id
service_id
state
requested_commit
resolved_commit
requested_by

source_snapshot          JSON
source_fingerprint       SHA-256 hex

release_name
release_path

previous_current_path    nullable
managed_dropin_path

health_check_snapshot    JSON

prepare_operation_id     nullable
activate_operation_id    nullable

failure_code
failure_message

queued_at
prepared_at              nullable
started_at               nullable
completed_at             nullable
updated_at
```

`source_snapshot` contains only non-secret systemd metadata:

```text
unit_name
fragment_path
drop_in_paths
user
group
working_directory
exec_start_path
exec_start_argv
environment_file_paths
restart_policy
restart_delay
source_file_hashes
```

Environment file contents and environment variable values are never stored.

### 6.2 Release provenance

Existing `Release` currently requires a `Deployment`. Stage B3 must allow a successful takeover to become the first managed release.

Change `Release.deployment` to nullable and add a nullable one-to-one `takeover` reference.

Add a database check constraint requiring exactly one provenance source:

```text
(deployment IS NOT NULL) XOR (takeover IS NOT NULL)
```

A takeover release row is created only after successful activation. A prepared or rolled-back takeover does not create an active `Release` row.

This keeps the existing deployment engine compatible: later managed deployments can discover the takeover release through the existing `service.releases` relation and `activated_at`.

### 6.3 Concurrency constraint

Only one non-terminal takeover may exist for a service.

Active states are:

```text
queued
inspecting
preparing
prepared
activating
verifying
```

Use a conditional unique constraint on `service` for these states.

Terminal states are:

```text
succeeded
failed
rolled_back
rollback_failed
canceled
```

## 7. Admission rules

Prepare is accepted only when all conditions pass:

```text
service.lifecycle_state == configured
service.executor == systemd
service.runtime == node-nextjs
service.inventory_status == present
service.unit_name is non-empty
service.repository is non-empty
service.root_directory is non-empty
service.service_port is set
server.status == online
server.disk_percent < 90
requested commit is exactly 40 lowercase hexadecimal characters
no active takeover exists for the service
```

Disk usage `>= 80%` is recorded as a warning. Disk usage `>= 90%` blocks takeover, matching existing deployment admission behavior.

The first implementation also requires the effective systemd `User` to be a non-root user. This prevents release clone/build work from being performed as root.

## 8. Exact commit rule

Takeover never accepts `latest`, branch names, tags, or arbitrary refs as the requested execution target.

The caller supplies an exact lowercase 40-character Git commit.

The Agent verifies that the commit exists in the configured repository before build.

For the first production acceptance, the exact commit must be the **Stage B3 commit that has already been deployed to the Control Plane at the time of takeover**. The current Stage B2 commit `6b4c43fd431d1a0082dc7b1b425000badd6035b0` is the pre-B3 baseline, not the final takeover target.

This avoids taking over the Web service into an older application revision after Stage B3 has been deployed.

## 9. Stable source inspection and fingerprint

The Agent inspects the source unit during PREPARE.

### 9.1 Effective metadata

Read:

```text
FragmentPath
DropInPaths
User
Group
WorkingDirectory
ExecStart
EnvironmentFiles
Restart
RestartUSec
```

Do not include runtime-only values such as PID, process start time, or transient systemd execution metadata in the fingerprint.

### 9.2 Source file hashes

Hash the exact bytes of:

- the fragment unit file,
- every existing drop-in file, sorted by absolute path.

The fingerprint is SHA-256 over canonical JSON containing:

```text
unit identity
selected stable effective values
sorted {path, sha256} source-file entries
```

Before ACTIVATE mutates anything, the Agent performs the same inspection again.

If the new fingerprint differs from `source_fingerprint`, activation stops with:

```text
service_configuration_changed
```

No service mutation occurs.

This protects manual administrator changes made between prepare and activate.

## 10. Immutable release layout

Reuse the existing release engine and its current naming convention.

```text
/srv/digitalafarin/apps/
└── digitalafarin-platform/
    └── platform-web/
        ├── releases/
        │   └── <UTC timestamp>-<sha7>/
        ├── shared/
        └── current -> releases/<release-name>
```

The full repository is checked out into the release directory. Build commands run only within the configured `root_directory`.

For `platform-web`:

```text
<release>/apps/web
```

The release is not linked as `current` during PREPARE.

## 11. Release preparation isolation

The Agent owns privileged directory setup but repository and build commands run as the source service user discovered from systemd.

For the first candidate:

```text
service user = deploy
```

Required behavior:

1. validate project/service slugs using existing safe identity rules,
2. derive the service root; never accept it from the caller,
3. create the service root/release directories under the approved apps root,
4. ensure the source service user can write the new release,
5. clone the configured repository as the source service user,
6. detach checkout at the exact requested commit,
7. validate `root_directory`,
8. run the existing Node recipe:
   - `npm ci`
   - `npm run build`
9. require successful build completion,
10. validate expected artifacts before returning `prepared`.

For `node-nextjs`, validation requires:

```text
<root>/package.json
<root>/package-lock.json
<root>/.next/
```

Stage B3 does not copy `/etc/digitalafarin-platform/web.env` into the release and does not persist its contents. Runtime secrets remain managed by the existing systemd `EnvironmentFile`.

## 12. Managed systemd drop-in

The base unit remains untouched.

Stage B3 owns exactly one derived path:

```text
/etc/systemd/system/<unit_name>.d/90-digitalafarin-managed.conf
```

For the first candidate:

```ini
[Service]
WorkingDirectory=/srv/digitalafarin/apps/digitalafarin-platform/platform-web/current/apps/web
```

The drop-in does not override:

```text
User
Group
EnvironmentFile
ExecStart
Restart
RestartSec/RestartUSec
```

The drop-in is written atomically:

1. create a temporary file in the same `.d` directory,
2. write validated content,
3. fsync/close,
4. set owner `root:root`,
5. set mode `0644`,
6. atomic rename to `90-digitalafarin-managed.conf`.

If that exact managed drop-in path already exists while the Service is still `configured`, prepare/activation fails with a managed-drop-in conflict. Stage B3 never overwrites an unknown file at its reserved path.

Other drop-ins are never modified.

## 13. Protected-service boundary

The existing generic systemd executor continues to reject protected units:

```text
digitalafarin-platform-*
digitalafarin-vps-mcp*
digitalafarin-telegram-mcp*
```

Stage B3 does **not** remove or weaken this rule.

Instead, it introduces takeover-specific execution paths whose inputs are derived from a validated `ServiceTakeover` execution context.

Generic operations remain:

```text
service.start / stop / restart
→ protected unit
→ BLOCK
```

Controlled takeover is:

```text
service.takeover.prepare / service.takeover.activate
→ service_id + takeover_id from typed Operation
→ Control Plane execution context
→ exact configured unit
→ dedicated takeover validation
→ narrow privileged execution
```

No caller supplies a shell command, executable, systemd action, filesystem path, or unit name to the Agent.

## 14. PREPARE operation

Introduce:

```text
service.takeover.prepare
```

Operation payload stored in the Control Plane:

```json
{
  "takeover_id": "<uuid>"
}
```

The Agent receives an execution context built server-side containing validated:

```text
takeover_id
service_id
project_slug
service_name
unit_name
repository
exact_commit
runtime
root_directory
install_configuration
build_configuration
service_port
health_check
```

Prepare flow:

```text
inspect source unit
→ calculate source fingerprint
→ validate service user
→ validate disk/path prerequisites
→ prepare exact-commit release
→ run build as source service user
→ validate build artifacts
→ return source snapshot + fingerprint + release metadata
```

PREPARE performs:

- no `current` symlink activation,
- no managed drop-in write,
- no `daemon-reload`,
- no service restart.

The server validates the result, persists the snapshot and release metadata, and transitions the takeover to `prepared`.

## 15. ACTIVATE operation

Activation is a separate explicit action.

Introduce:

```text
service.takeover.activate
```

It can be queued only for a takeover in `prepared`.

Server-side execution context includes the persisted:

```text
source_fingerprint
release_path
release_name
health_check_snapshot
derived service_root
derived managed_dropin_path
derived managed_working_directory
```

Activation flow:

```text
re-inspect source service
→ compare fingerprint
→ validate prepared release still exists
→ record existing current target, if any
→ atomic current symlink activation
→ atomic managed drop-in installation
→ systemctl daemon-reload
→ restart exact configured unit
→ verify health
→ success OR rollback
```

## 16. Health verification

Reuse the existing loopback-only HTTP health mechanism.

For the first `platform-web` takeover:

```text
URL:             http://127.0.0.1:9751/
expected status: 200
timeout:         bounded by existing health checker
```

A takeover success requires **two consecutive successful health checks**. The second check occurs after a one-second stabilization interval.

This is stricter than the current deployment engine's single successful response while still reusing its URL validation and bounded request behavior.

The health snapshot used by activation is frozen at PREPARE completion so configuration changes after prepare cannot silently alter the acceptance contract.

## 17. First-takeover rollback

The first takeover is different from later managed deployments because `current` may not have existed before activation and the service currently runs directly from:

```text
/opt/digitalafarin-platform/apps/web
```

If new health verification fails:

1. restore the previous `current` target if one existed,
2. otherwise restore the previous absence of `current`,
3. remove the Stage B3 managed drop-in,
4. `systemctl daemon-reload`,
5. restart the exact unit,
6. verify the original service health using the same loopback contract.

Because the base unit is untouched, removing the managed drop-in restores:

```text
WorkingDirectory=/opt/digitalafarin-platform/apps/web
```

If original health passes:

```text
takeover.state = rolled_back
service.lifecycle_state = configured
```

If original health does not pass:

```text
takeover.state = rollback_failed
service.lifecycle_state = configured
```

A `rollback_failed` service is not considered managed and subsequent deployment/takeover actions are blocked pending operator intervention.

## 18. Filesystem cleanup

On successful takeover:

- retain the activated release,
- use the existing managed release retention mechanism for later deployments.

On a health failure followed by successful rollback:

- ensure the failed release is not `current`,
- remove the failed prepared release after rollback verification to avoid unnecessary disk consumption.

On `rollback_failed`:

- retain the prepared release and takeover metadata for forensic investigation.

On `canceled` while `prepared`:

- lifecycle becomes terminal so another takeover can be prepared,
- the inactive prepared directory may remain temporarily,
- it is eligible for later bounded cleanup and is never treated as an active `Release`.

## 19. Final success transaction

The Agent returns structured activation events and final state through the existing operation completion channel.

The Control Plane validates the result.

For `succeeded`, one database transaction performs:

1. create a `Release` linked to the `ServiceTakeover`,
2. set `Release.activated_at`,
3. set `ServiceTakeover.state = succeeded`,
4. set completion timestamps,
5. set `Service.lifecycle_state = managed`,
6. create final audit records.

`managed` is therefore never visible before health has passed.

For `rolled_back`, no active `Release` row is created.

## 20. API

### Prepare takeover

```text
POST /api/control/v1/services/{service_id}/takeovers/
```

Body:

```json
{
  "commit": "<exact lowercase 40-char SHA>"
}
```

Returns takeover metadata and the prepare operation.

### Get takeover

```text
GET /api/control/v1/takeovers/{takeover_id}/
```

Includes non-secret snapshot summary, release metadata, operation IDs, timestamps, and state.

### Activate prepared takeover

```text
POST /api/control/v1/takeovers/{takeover_id}/activate/
```

No caller-controlled execution payload.

### Cancel prepared takeover

```text
POST /api/control/v1/takeovers/{takeover_id}/cancel/
```

Allowed only before activation. It marks the takeover terminal and never mutates systemd.

### Service takeover history

```text
GET /api/control/v1/services/{service_id}/takeovers/
```

## 21. MCP

Add strictly typed tools:

```text
vps_prepare_service_takeover(service_id, commit)
vps_get_service_takeover(takeover_id)
vps_activate_service_takeover(takeover_id)
vps_cancel_service_takeover(takeover_id)
```

No tool accepts:

```text
shell
command
unit_name
filesystem path
systemctl action
environment values
```

The Control Plane derives all execution-sensitive details from existing service/takeover metadata.

## 22. Web UI

The configured service detail page gets a `Controlled takeover` section.

Before prepare it shows:

```text
Lifecycle
Unit
Runtime
Protected status
Inventory status
Repository
Branch
Root directory
Port
```

The user enters only an exact commit.

After prepare, the UI displays:

```text
Prepared commit
Source fingerprint
Release name
Current source working directory
Proposed managed working directory
Health target
```

The user then explicitly chooses activation.

Because the existing Agent protocol does not stream phase events, Stage B3 does not introduce a new live-progress transport. While an operation is running, UI shows operation-level state. After completion, it renders the validated takeover event timeline returned by the Agent.

This keeps Stage B3 aligned with the existing deployment operation architecture.

## 23. Audit events

Required events:

```text
service.takeover.requested
service.takeover.inspected
service.takeover.prepared
service.takeover.canceled
service.takeover.activation_requested
service.takeover.activation_started
service.takeover.health_passed
service.takeover.succeeded
service.takeover.failed
service.takeover.rollback_started
service.takeover.rolled_back
service.takeover.rollback_failed
```

Audit metadata may include:

```text
service_id
takeover_id
server_id
unit_name
exact_commit
release_name
source_working_directory
managed_working_directory
health_port
source_fingerprint
```

No secret values are included.

## 24. Error codes

At minimum:

```text
service_not_configured
unsupported_takeover_runtime
inventory_unit_missing
server_offline
disk_usage_blocked
invalid_exact_commit
takeover_already_active
takeover_not_prepared
takeover_already_terminal
source_user_unsafe
service_configuration_changed
managed_dropin_conflict
release_prepare_failed
release_validation_failed
takeover_activation_failed
takeover_health_failed
takeover_rollback_failed
```

Errors exposed to API/MCP remain bounded and redacted.

## 25. Testing strategy

### API/model tests

Cover:

```text
configured node service can prepare
adopted service cannot prepare
managed service cannot prepare
unsupported runtime cannot prepare
missing inventory blocks prepare
offline server blocks prepare
disk >= 90 blocks prepare
non-exact SHA blocks prepare
two active takeovers are rejected
prepared takeover can activate
non-prepared takeover cannot activate
prepared takeover can be canceled
success changes Service to managed
failure leaves Service configured
rolled_back leaves Service configured
rollback_failed leaves Service configured
Release provenance constraint accepts deployment XOR takeover only
```

### Agent tests

Cover:

```text
stable systemd snapshot excludes runtime PID/time
unit/drop-in file change changes fingerprint
paths are derived under approved roots
path escape is rejected
repository/build commands run as source service user
root source user is rejected for Stage B3
exact commit checkout is required
Next artifacts are validated
PREPARE never writes current/drop-in and never restarts
ACTIVATE rejects fingerprint drift
managed drop-in is atomic and derived
generic protected restart remains blocked
takeover-specific restart accepts only validated execution context
health requires two successful loopback checks
first takeover rollback removes managed drop-in
first takeover rollback restores absence of current when appropriate
rollback restores original health
rollback failure is reported without claiming managed state
```

### MCP tests

Cover strict schemas and verify no arbitrary command/path/unit input exists.

### Web tests

Cover:

```text
takeover section only for configured services
exact commit validation
prepare response rendering
prepared summary rendering
activate confirmation
managed services no longer show takeover preparation
operation/event timeline rendering
```

### Production acceptance

For `platform-web`:

```text
1. Stage B3 Control Plane code deployed and healthy.
2. Service remains configured and current unit remains unchanged.
3. Prepare exact Stage B3 production commit.
4. Verify no restart occurred during PREPARE.
5. Verify persisted source snapshot and fingerprint.
6. Activate takeover.
7. Verify exactly one controlled service restart.
8. Verify two successful health responses on 127.0.0.1:9751/.
9. Verify lifecycle_state == managed.
10. Verify systemd WorkingDirectory points into /srv/.../current/apps/web.
11. Verify User/Group/EnvironmentFile/ExecStart remain unchanged.
12. Verify generic protected restart is still rejected.
13. Verify no Oily/KhoshVisa service was mutated.
```

## 26. Rollout plan

Stage B3 implementation is developed on a dedicated feature branch.

Production rollout order:

```text
deploy Stage B3 code
→ run migrations
→ rebuild Web
→ install MCP/Agent package changes
→ restart Platform API/MCP/Web/Agent as required
→ verify Control Plane health
→ verify takeover endpoints/tools without takeover
→ PREPARE platform-web
→ inspect persisted prepared state
→ ACTIVATE platform-web
→ verify managed state/systemd/health/audit
```

Oily is explicitly excluded from the first production takeover.

## 27. Safety invariants

The implementation is not acceptable unless all invariants hold:

1. `managed` means a health-verified controlled takeover has succeeded.
2. PREPARE cannot restart or mutate the target service.
3. ACTIVATE cannot proceed after source fingerprint drift.
4. Caller input cannot become a shell command, arbitrary unit, or arbitrary filesystem path.
5. Generic protected-service operations remain blocked.
6. The base systemd unit is never rewritten by Stage B3.
7. Runtime secret values never enter takeover snapshots, events, or audit metadata.
8. Rollback behavior is defined before activation begins.
9. Failed or rolled-back takeover never changes Service to `managed`.
10. The first production candidate is DigitalAfarin Platform Web, not Oily.

## 28. Future extensions

After the first `node-nextjs + systemd` takeover is proven in production:

- extend takeover recipes to `python-django`,
- handle Django virtualenv/release-specific runtime requirements,
- add stronger release cleanup/reconciliation,
- consider blue/green port switching for services that require lower downtime,
- consider takeover of API/MCP only after self-hosting failure modes are separately designed,
- then evaluate Oily adoption/takeover as a separate rollout.

These are future extensions and are not part of Stage B3 acceptance.
