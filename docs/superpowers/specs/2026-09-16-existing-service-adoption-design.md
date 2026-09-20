# Stage B2 — Existing Service Adoption Design

**Date:** 2026-09-16
**Status:** Approved
**Scope:** Safe adoption of existing systemd services plus deployment metadata configuration. Controlled takeover is explicitly deferred to Stage B3.

## 1. Context

DigitalAfarin Platform already has two different concepts that must remain distinct:

- `ServiceSnapshot` is inventory reported by the Host Agent. It represents the current observed systemd unit state on a specific server.
- `Service` is currently a deployment-managed application definition. It requires repository/runtime/port metadata and the deployment execution context derives the systemd unit name as `<project-slug>-<service-name>.service`.

The current deployment engine builds immutable releases under `/srv/digitalafarin/apps/<project>/<service>/releases/...`, switches the `current` symlink, then restarts a systemd unit. It does not rewrite an existing unit file or prove that the unit already points at the Platform-managed release tree.

That means an existing production unit such as `oily-backend.service` cannot safely become deployment-managed merely by recording repository metadata. A release could be built successfully while the existing unit still executes code from another path.

Stage B2 therefore introduces **adoption without takeover**.

## 2. Goal

Allow an operator to attach a real, already-running systemd unit from server inventory to a Platform Project without changing that unit or its workload.

After adoption the Platform can:

- show the service under the selected Project;
- retain the real server and `unit_name` binding;
- show current inventory/systemd state when available;
- record deployment metadata for future use;
- expose the service through typed API/MCP/UI flows;
- preserve independent protected-unit policy;
- guarantee that adoption itself creates no Agent operation and causes no restart, stop, deploy, unit rewrite, Nginx change, or workload downtime.

## 3. Non-goals

Stage B2 does **not**:

- take control of an existing systemd unit;
- rewrite or install unit files;
- change `ExecStart`, `WorkingDirectory`, environment files, users/groups, or permissions of an existing workload;
- restart, stop, start, or deploy an adopted/configured service as part of adoption;
- transition an adopted service to deployment-managed state;
- migrate existing application files into `/srv/digitalafarin/apps/...`;
- implement takeover rollback.

Those responsibilities belong to **Stage B3 — Controlled Takeover**.

## 4. Lifecycle

`Service.lifecycle_state` has three states:

```text
adopted -> configured -> managed
```

Meaning:

- `adopted`: bound to a real inventory unit; no deployment configuration is required; deployment actions are blocked.
- `configured`: full deployment metadata has been validated and stored; deployment actions remain blocked because takeover has not happened.
- `managed`: Platform owns deployment execution for the service. Existing Service records are backfilled to this state for backward compatibility. Transition from `configured` to `managed` is **not implemented in Stage B2**; Stage B3 owns that transition.

Inventory-only units are not Service records. They remain `ServiceSnapshot` rows until explicitly adopted.

## 5. Data Model

### 5.1 Service changes

Add:

- `unit_name: CharField(max_length=255)`
- `lifecycle_state: CharField(choices=[adopted, configured, managed])`

Deployment-specific fields become database-nullable so an `adopted` row can exist without fake metadata:

- `repository`
- `branch`
- `root_directory`
- `runtime`
- `service_port`

`install_configuration` and `build_configuration` may remain empty dictionaries for adopted services.

The normal managed-service creation serializer continues to require complete deployment metadata. Database nullability must not weaken the existing managed creation contract.

### 5.2 Constraints

Retain:

- unique `(project, name)`

Add:

- unique `(target_server, unit_name)`

A real systemd unit on one server can therefore belong to only one Platform Service record.

### 5.3 Existing managed Service migration

Existing Service rows are deployment-managed today. Migration backfills:

```text
lifecycle_state = managed
unit_name = f"{project.slug}-{service.name}.service"
```

Before adding the unique `(target_server, unit_name)` constraint, the data migration checks for duplicate backfilled bindings. If any duplicates exist, migration aborts rather than silently selecting one.

After backfill, `unit_name` becomes non-null.

No workload, Agent, systemd unit, release, or Deployment row is mutated by this migration.

## 6. Inventory Relationship

`ServiceSnapshot` remains the source of observed systemd status.

Adoption validates that a snapshot exists for:

```text
(server, unit_name)
```

No foreign key from `Service` to `ServiceSnapshot` is added because heartbeat inventory is ephemeral: snapshots that disappear from the latest heartbeat are currently deleted. Binding must therefore use stable values on `Service` (`target_server`, `unit_name`), not snapshot row identity.

Project/service API representations derive inventory state at read time:

- snapshot exists: expose `load_state`, `active_state`, `sub_state`, `last_seen_at` and `inventory_status = present`;
- snapshot absent: keep the Service record and return `inventory_status = missing`.

Missing inventory never deletes an adopted Service or its audit history.

## 7. Adoption API

### 7.1 Endpoint

```http
POST /api/control/v1/projects/{project_id}/services/adopt/
```

Request body is intentionally narrow:

```json
{
  "server_id": "<server UUID>",
  "unit_name": "oily-backend.service",
  "name": "backend"
}
```

No repository, command, path, environment, package, systemd config, or arbitrary payload is accepted.

### 7.2 Validation

The API must:

1. resolve an active target Server by UUID;
2. verify `unit_name` matches the existing safe unit-name validation pattern;
3. verify `ServiceSnapshot(server, unit_name)` currently exists;
4. validate `name` as a safe service slug;
5. reject duplicate `(project, name)`;
6. reject duplicate `(target_server, unit_name)`;
7. create a `Service` with:
   - `executor = systemd`
   - `lifecycle_state = adopted`
   - deployment metadata unset/null;
8. write an audit event `service.adopted` containing only identifiers and non-secret metadata.

### 7.3 Side-effect invariant

A successful adoption request must not create any `Operation` row.

This is a testable Stage B2 invariant.

## 8. Deployment Configuration API

### 8.1 Endpoint

```http
PUT /api/control/v1/services/{service_id}/deployment-configuration/
```

The request replaces the complete deployment configuration for an adopted/configured service:

- `repository`
- `branch`
- `root_directory`
- `runtime`
- `install_configuration`
- `build_configuration`
- `service_port`

The same allowlists and safe path/ref validation already used by managed Service creation are reused rather than duplicated.

### 8.2 State behavior

- `adopted` + valid complete configuration -> `configured`
- `configured` + valid complete configuration -> stays `configured`
- `managed` -> Stage B2 configuration endpoint rejects the request; existing managed-service editing is outside this scope

Configuration writes `service.deployment_configured` audit events with identifiers and field names, never secret values.

Configuration does not create an Operation and does not inspect or modify the live unit file.

## 9. Deployment Safety Gate

All deployment entry points must require:

```text
service.lifecycle_state == managed
```

This check belongs in the deployment domain/service layer (`queue_deployment` and `queue_rollback`), not only in the Web UI.

Therefore API, Web, MCP, or any future caller cannot deploy an `adopted` or `configured` Service by bypassing presentation logic.

Blocked requests return a stable conflict response such as:

```json
{
  "error": "service_not_managed",
  "message": "Service has not completed controlled takeover."
}
```

Existing migrated Service rows remain `managed`, preserving current deployment behavior.

## 10. Explicit Unit Name in Deployment Execution

After Stage B2, managed deployment execution must use:

```python
service.unit_name
```

instead of recomputing:

```python
f"{service.project.slug}-{service.name}.service"
```

For all existing managed rows the migration backfills exactly that old computed value, so behavior remains unchanged.

This change prepares the execution model for Stage B3, where an adopted real unit may eventually become managed only after controlled takeover proves the binding is correct.

## 11. Protected Units

Protected-unit policy remains independent from lifecycle state and database data.

Examples such as:

```text
digitalafarin-platform-*
```

remain protected by the existing centralized API/Agent rules.

A protected unit may be adopted for inventory/UI validation, including a DigitalAfarin Platform service, but adoption does not grant restart/deploy permission. Stage B2 never weakens protected-unit checks.

Protection status should be derived from the same policy helper used by typed service operations and may be exposed read-only in API/UI representation.

## 12. Web UI

### 12.1 Project page: Adopt existing service

Add an `Existing services` panel.

Flow:

1. choose a Server;
2. load its inventory units;
3. hide or disable units already bound to a Service;
4. select a unit;
5. enter a Project-local service slug/name;
6. submit `Adopt`.

The server selection may use a query parameter and server-side rendering to avoid adding a client-state subsystem solely for this form.

Protected units are visibly labelled, not hidden, because the first acceptance test may intentionally adopt a Platform unit. The UI explains that protected status remains active.

### 12.2 Project service list

Each Service row/card shows:

- display/service name;
- `unit_name`;
- lifecycle badge (`Adopted · Unmanaged`, `Configured · Unmanaged`, `Managed`);
- live inventory state (`running`, `inactive`, `failed`, `missing`);
- protected indicator where applicable.

### 12.3 Service detail page

For `adopted`:

- show unit/server/inventory status;
- show `Configure deployment` form;
- do not render Deploy/Redeploy/Rollback controls.

For `configured`:

- show validated deployment metadata;
- show `Configured · Management disabled`;
- explicitly state that Controlled Takeover is Stage B3;
- do not render Deploy/Redeploy/Rollback controls.

For `managed`:

- preserve the current deployment UI and deployment history.

Presentation is not the security boundary; domain-layer lifecycle checks remain mandatory.

## 13. MCP Surface

Add narrow typed tools so ChatGPT can perform the same metadata-only workflow without arbitrary commands:

```text
vps_adopt_service(project_id, server_id, unit_name, name)
vps_configure_service_deployment(service_id, repository, branch, root_directory, runtime, service_port, install_configuration, build_configuration)
```

Requirements:

- no shell/command/systemd-config/path injection surface beyond already validated structured fields;
- adoption tool maps only to the adoption endpoint;
- configuration tool maps only to the configuration endpoint;
- neither tool queues Agent operations;
- returned data is secret-free;
- existing list/get project responses expose lifecycle and inventory-derived status.

No MCP tool for `configured -> managed` is added in Stage B2.

## 14. Agent Impact

No new Agent operation kind or Agent capability is required for Stage B2.

The Host Agent continues to report inventory exactly as before. All Stage B2 writes are Control Plane metadata writes.

The only deployment-related compatibility change is on the API side: execution context for already-managed services uses persisted `service.unit_name` rather than recomputing it.

## 15. Auditability

Add events:

- `service.adopted`
- `service.deployment_configured`

Recommended metadata:

```json
{
  "project_id": "...",
  "server_id": "...",
  "unit_name": "...",
  "service_name": "..."
}
```

Configuration audit metadata may include which configuration keys changed, but never plaintext environment secrets, credentials, repository credentials, or command output.

## 16. Error Handling

Stable errors should distinguish:

- server not found/inactive;
- inventory unit not found;
- unit already adopted;
- Project service name already used;
- invalid unit/name/configuration;
- service lifecycle does not allow configuration;
- service is not managed when deployment is requested.

Concurrent duplicate adoption is ultimately protected by the database unique constraint even if two requests pass pre-validation at nearly the same time. Integrity errors are normalized into a safe conflict response.

## 17. Test Plan

### API / Django

Must cover:

1. adopt a real snapshot successfully;
2. adoption creates `Service(lifecycle_state=adopted)` with real `unit_name`;
3. adoption creates no `Operation`;
4. reject nonexistent inventory unit;
5. reject duplicate `(server, unit_name)`;
6. reject duplicate `(project, name)`;
7. protected unit can be adopted without changing protected mutation behavior;
8. missing future snapshot leaves Service intact and reports `inventory_status=missing`;
9. configure complete metadata moves `adopted -> configured`;
10. invalid/partial deployment metadata is rejected;
11. configuration creates no `Operation`;
12. deployment of `adopted` service is blocked;
13. deployment of `configured` service is blocked;
14. rollback/redeploy paths are blocked for non-managed services;
15. existing migrated managed Service deployment behavior remains green;
16. execution context uses persisted `service.unit_name`.

### Migration

Must cover or verify:

- existing rows become `managed`;
- backfilled `unit_name` equals the old computed unit name;
- duplicate preflight aborts rather than corrupting bindings;
- managed rows retain repository/runtime/port data.

### MCP

Must cover:

- typed tool contract exposes adoption/configuration only;
- exact request mapping;
- invalid identifiers/configuration are normalized safely;
- no arbitrary command/config fields;
- existing static banned-fragment/security contract remains green.

### Web

Must cover:

- adopted service displays `Adopted · Unmanaged` and no Deploy action;
- configured service displays management-disabled state and no Deploy action;
- managed service retains current Deploy action;
- missing inventory is visible without deleting the Project Service;
- adoption form emits only the narrow structured request;
- protected units are labelled.

## 18. Production Rollout

Stage B2 rollout is additive and designed for no workload downtime:

1. verify clean repo and database backup/rollback readiness;
2. deploy API code compatible with migration;
3. run the additive Service migration and duplicate-binding preflight;
4. deploy Web and MCP updates;
5. restart only Platform control-plane components necessary to load new code;
6. do not restart adopted workload services;
7. verify existing managed Service records remain `managed` and retain old unit bindings;
8. adopt one protected DigitalAfarin Platform unit as the first metadata-only acceptance case;
9. verify Project UI shows the adopted service and current inventory state;
10. verify Operation count did not increase because of adoption;
11. configure deployment metadata on the acceptance service only if useful for UI/API validation; do not enable management;
12. after acceptance, adopt Oily services one at a time without takeover or restart.

## 19. Stage B2 Acceptance Criteria

Stage B2 is complete when:

- a real existing unit can be adopted from inventory into a Project;
- adoption is metadata-only and produces no Agent Operation;
- real `unit_name` and target server binding are persisted uniquely;
- adopted/configured services remain undeployable by API, MCP, and UI;
- inventory disappearance is shown as missing without deleting adoption history;
- protected-unit policy remains intact;
- existing managed Service deployments continue to work unchanged;
- deployment metadata can be stored and validated without takeover;
- UI clearly distinguishes `Adopted · Unmanaged`, `Configured · Unmanaged`, and `Managed`;
- no `configured -> managed` transition exists in Stage B2.

## 20. Stage B3 Boundary

Stage B3 will design and implement Controlled Takeover. It must inspect the existing unit execution contract (`ExecStart`, `WorkingDirectory`, environment, user/group, paths), generate or reconcile the Platform-managed unit/release contract, present a preflight/diff, perform an explicitly approved cutover, health-check the new execution path, and preserve a rollback path to the previous unit configuration.

Stage B2 intentionally does not pre-decide the exact Stage B3 unit rewrite mechanism beyond preserving the real `unit_name` and validated deployment metadata required for that future design.
