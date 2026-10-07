# Typed Coolify management

This incremental layer preserves `ChatGPT → DigitalAfarin MCP → Django Control
Plane → Coolify API`. The host Agent, systemd controls, protected units, tunnel,
and existing inventory tools are unchanged. It performs no production rollout
or workload migration.

The starting point is GitHub `main` at `e9b1739` (read-only Coolify integration).
The API contracts were checked against Coolify **4.3.23**, tag commit
`e2e2d4010bcd590084b66d6f748f3eec8e2bbee9`, rather than unversioned API examples:

- [Routes](https://github.com/coollabsio/coolify/blob/v4.3.23/routes/api.php)
- [Applications controller](https://github.com/coollabsio/coolify/blob/v4.3.23/app/Http/Controllers/Api/ApplicationsController.php)
- [Deployments controller](https://github.com/coollabsio/coolify/blob/v4.3.23/app/Http/Controllers/Api/DeployController.php)
- [Database controller](https://github.com/coollabsio/coolify/blob/v4.3.23/app/Http/Controllers/Api/DatabasesController.php)
- [Services controller](https://github.com/coollabsio/coolify/blob/v4.3.23/app/Http/Controllers/Api/ServicesController.php)
- [API abilities](https://github.com/coollabsio/coolify/blob/v4.3.23/app/Http/Middleware/ApiAbility.php)
- [Sensitive-data middleware](https://github.com/coollabsio/coolify/blob/v4.3.23/app/Http/Middleware/ApiSensitiveData.php)

## Implementation map

| Layer | Files |
| --- | --- |
| Coolify HTTP transport and fixed operations | `apps/api/control/coolify_client.py` |
| Request validation | `apps/api/control/coolify_serializers.py` |
| Authorization policy and response projection | `apps/api/control/coolify_management.py` |
| Scoped Django actions and audit | `apps/api/control/coolify_management_views.py`, `control_urls.py` |
| Managed application registry | `models.py`, migration `0022_coolifymanagedapplication.py` |
| Policy configuration | `apps/api/platform_api/settings.py` |
| Explicit scope provisioning | `management/commands/create_service_principal.py`, `grant_coolify_scope.py` |
| MCP typed models and tools | `mcp/digitalafarin_vps_mcp/coolify.py`, `server.py` |
| MCP → Django requests | `mcp/digitalafarin_vps_mcp/control_plane.py` |
| Tests | API `test_coolify_client.py`, `test_coolify_management.py`; MCP `test_coolify.py`, tool inventory tests |
| CI | `.github/workflows/platform-ci.yml` adds the MCP suite and MCP path triggers |

Existing `coolify_get_status`, `coolify_list_servers`, `coolify_list_projects`, and
`coolify_list_resources`, and their endpoints, keep their names and contracts.

## Operations

All Django paths below are relative to `/api/control/v1/coolify/`. `A` means an
application UUID; `D` a deployment UUID; `P` a project UUID. Coolify identifiers
are bounded opaque strings, not necessarily RFC UUIDs. No endpoint or tool takes
an arbitrary upstream path, HTTP method, shell command, SQL, Dockerfile content,
Compose document, Docker option, hook, or custom build/start command.

| New MCP tool | Django method/path | Scope |
| --- | --- | --- |
| `coolify_list_management_targets` | GET `targets/` | read |
| `coolify_list_environments` | GET `projects/P/environments/` | read |
| `coolify_create_application` | POST `applications/` | manage |
| `coolify_configure_application` | POST `applications/A/configure/` | manage |
| `coolify_list_environment_variables` | GET `applications/A/environment/` | read |
| `coolify_create_environment_variable` | POST `applications/A/environment/create/` | manage |
| `coolify_update_environment_variable` | POST `applications/A/environment/update/` | manage |
| `coolify_deploy_application` | POST `applications/A/deploy/` | deploy |
| `coolify_redeploy_application` | POST `applications/A/redeploy/` | deploy |
| `coolify_start_application` | POST `applications/A/start/` | deploy |
| `coolify_stop_application` | POST `applications/A/stop/` | deploy |
| `coolify_restart_application` | POST `applications/A/restart/` | deploy |
| `coolify_list_deployments` | GET `applications/A/deployments/` | read |
| `coolify_get_deployment` | GET `applications/A/deployments/D/` | read |
| `coolify_get_deployment_logs` | GET `applications/A/deployments/D/logs/` | read |
| `coolify_delete_application` | POST `applications/A/delete/` | delete |

The scope prefix is `coolify:`. Scope membership is exact, with no wildcard,
implicit manage→delete grant, or use of `coolify:read` for writes. Existing
operator principals receive no additional write privileges automatically.

New Coolify client methods:

- Placement: `list_environments`, `get_environment`, `list_server_resources`.
- Applications: `create_application`, `create_github_application`,
  `get_application`, `update_application`, `delete_application`.
- Variables: `list_environment_variables`, `create_environment_variable`,
  `update_environment_variable`.
- Deployment/lifecycle: `deploy_application`, `start_application`,
  `stop_application`, `restart_application`, `get_deployment`,
  `list_application_deployments`. Redeploy uses `deploy_application(force=True)`.

Creation selects a named, administrator-reviewed target. The target resolves
project/environment/server/destination UUIDs; callers cannot substitute a
production placement. Public HTTPS Git URLs are supported. An optional
server-side `github_app_uuid` selects Coolify's private GitHub App endpoint;
GitHub credentials never travel through MCP.

Settings include an approved repository, branch, repository-relative root and
publish directories, `nixpacks`/`railpack`/`static`/`dockerfile` build pack,
container-exposed/internal ports, approved HTTPS domains, static mode, memory,
and CPU limits. Commands remain in reviewed repository configuration. Building
an approved repository necessarily executes that repository's code: the
repository/branch maintainers and target administrator are part of the trust
boundary. Direct host port publishing is deliberately excluded; the Coolify
proxy routes approved domains to container ports.

Creation disables instant deployment, automatic deployment, preview deployment,
and autogenerated domains. Deploy and start queue a normal deployment; redeploy
forces a rebuild; restart uses Coolify's restart-only queue. A skipped deployment
is reported as `queued=false`, not fabricated success. Stop disables Docker
cleanup. Delete requires `coolify:delete` and an exact matching
`confirm_application_uuid`, and explicitly preserves volumes, networks, and
configuration while disabling Docker cleanup. Deletion is asynchronous; the
local registry immediately disables further operations, but does not claim the
upstream deletion job has finished.

## Authorization, audit, and confidentiality

Writes are disabled until `COOLIFY_MANAGEMENT_TARGETS` is configured. Every
application action additionally requires:

1. An authenticated active service principal with an unrevoked credential and
   the exact action scope.
2. A local `CoolifyManagedApplication` record created by this layer, owned by
   that principal, not deleted.
3. Current target authorization for that principal.
4. A non-protected application name, approved repository, and current membership
   in the approved project/environment and server, verified through Coolify.

The registry cannot import existing applications through MCP/API. Existing
production resources are therefore outside this management boundary. Removing
the target/principal from policy revokes management immediately. Renaming an
application to a platform/MCP/tunnel/Coolify name also blocks it. This adds a new
boundary without modifying existing VPS protection rules.

A creation `request_id` (RFC UUID) is reserved before the upstream call. Duplicate
submissions cannot create another application, including after a timeout. A
pending row with no application UUID needs administrator reconciliation in
Coolify; do not blindly submit a fresh request ID. Other actions are not
transactional with Coolify and are not automatically retried. If a timeout or
502 occurs, inspect state before retrying. There is no claim of exactly-once
execution across the two systems.

Audit events record action, principal, application identifier, registration
request ID, and safe HTTP result. Scope denials for authenticated principals are
audited. Payloads, variable values, upstream error messages, repository content,
and log text are never included. The upstream token exists only in Django.
Transport disables redirects and retries, has a 10-second timeout per upstream
request (MCP allows 60 seconds for the aggregate Control Plane operation), caps decoded
responses at 2 MiB, and emits generic errors instead of upstream response bodies.

Variable names must be administrator-approved. Values are write-only, limited
to 16 KiB, sent as literal values, and marked shown-once. Preview variables are
excluded. Build/runtime delivery flags are explicit. Buildpack command/control
variables are rejected even if accidentally placed in the policy. Values are
not stored in the registry or audit, and reads project only approved names and
boolean delivery flags. No variable values or comments are returned.

Deployment responses project only identifiers and a fixed status enum. Because
Coolify hides `Application.id`, deployment ownership is derived from the
application-scoped deployment list and checked against the requested deployment.
Configuration snapshots, diffs, commits/messages, commands, and URLs are omitted.

Logs are capped at 200 records. Only an exact allow-list of constant Coolify
lifecycle messages is retained (for example `Building docker image completed.`).
All other output becomes `[REDACTED]`; prefixes, suffixes, exception text,
connection strings, multiline keys, and even apparently harmless build output
are not passed through. This is intentionally stricter than regex scrubbing,
which cannot guarantee removal of shared/server/build credentials. Arbitrary
compiler diagnostics must be inspected by an authorized administrator in
Coolify. Without `read:sensitive`, Coolify omits logs; the response correctly
reports `available=false` rather than an empty successful log read.

## Future production configuration (not performed by this PR)

After review and a separate rollout approval:

- Apply migration `0022`; deploy API and MCP through the existing reviewed
  GitHub/systemd conventions. No Agent or VPS privilege change is required.
- Keep `COOLIFY_BASE_URL` and `COOLIFY_API_TOKEN` in the Django service environment
  only. Use a dedicated Coolify team and a token with `read`, `write`, and `deploy`
  abilities, not `root`. In 4.3.23, write/deploy abilities require an admin/owner
  of that team. Optional `read:sensitive` enables the redacted log projection;
  it is not necessary for application management.
- Configure reviewed `COOLIFY_MANAGEMENT_TARGETS` JSON. Empty policy is the
  default. Example (identifiers and repositories are placeholders):

```json
{
  "migration-staging": {
    "principals": ["chatgpt-vps-mcp"],
    "project_uuid": "reviewed-project",
    "environment_uuid": "reviewed-environment",
    "server_uuid": "reviewed-server",
    "destination_uuid": "reviewed-destination",
    "repositories": ["https://github.com/example/reviewed-app.git"],
    "domains": ["https://staging.example.com"],
    "environment_keys": ["DATABASE_URL", "APP_SECRET"]
  }
}
```

- For a private GitHub repository, add `github_app_uuid` to the target after
  installing/authorizing that app in Coolify. This is an identifier, not a token.
- Create a separate principal with `--profile coolify-manager`, or explicitly
  grant individual scopes to the existing identity using
  `python manage.py grant_coolify_scope NAME --scope coolify:manage` and
  `--scope coolify:deploy`. The command preserves credentials and audits grants.
  `coolify:delete` is a separate explicit grant; no manager/operator profile
  includes it. A principal can manage only its own registry entries.
- Configure DNS/proxy routing and approved repositories/buildpacks separately.
  Do not enroll Cafino, Oily, MCP, databases, or other current workloads through
  this PR. No migration/import shortcut is provided.

## PostgreSQL, Redis, and Compose investigation

These resource families have real APIs in 4.3.23, but are not interchangeable
with applications or necessary to establish this application management layer.
No database/Compose management tools are added in this PR.

| Resource | Verified API surface | Required narrow follow-up before migration |
| --- | --- | --- |
| PostgreSQL | POST `/databases/postgresql`; PATCH `/databases/{uuid}`; POST start/stop/restart; database and volume backup endpoints | Explicit database/user names, server-side credential references, pinned approved image, private networking, persistent volume ownership, backup/restore and rollback policy. No raw `postgres_conf`, init arguments, SQL, or public-port switch. |
| Redis | POST `/databases/redis`; typed database lifecycle routes | Approved image/version, server-side password provisioning, private networking, persistence/backup decisions. Do not expose raw `redis_conf`. |
| Other database families | Dedicated creation routes for supported engines | Engine-specific typed configuration and preservation semantics; do not use a generic resource/HTTP proxy. |
| Compose/services | POST `/services` accepts either catalog `type` or base64 `docker_compose_raw`; service lifecycle/environment APIs exist; applications also support the `dockercompose` build pack | Reviewed fixed service templates and versioned volume/network policy. Raw Compose permits arbitrary commands, privileged containers and host mounts, so it is intentionally rejected rather than exposed as a string tool. |

The existing DigitalAfarin systemd/PostgreSQL/volume machinery is not modified or
reused implicitly for Coolify resources. Database cutover, data import, restore,
and production retention remain separately reviewed migration work.

## 4.3.23 limitations and contract details

- Lifecycle writes use POST. Legacy GET start/stop/restart/deploy routes return
  a POST-required response.
- Delete defaults to deleting persistent assets; stop defaults to cleanup. This
  client explicitly opts out of those defaults.
- Start can trigger a build; it is not a guaranteed container-only start.
- `Application.id` is hidden; application-scoped deployment records are needed
  for ownership verification. GitHub URLs are stored as repository slugs.
- Multiple server destinations require an explicit destination UUID.
- Deployment logs have no bounded per-deployment tail endpoint here: the client
  caps the whole response before returning a bounded projection. Responses over
  2 MiB fail closed, even when the caller asks for only a few lines.
- Sensitive log availability requires both token ability and team admin/owner
  status. A read-only token cannot perform writes.
- Creation and delete are not an atomic transaction with Django; reconciliation
  after network uncertainty remains an administrator operation.
- API contract/mocked integration tests do not substitute for a future staging
  acceptance test against a disposable 4.3.23 instance. No production endpoint
  was contacted to validate writes.

See [validation results and baseline failures](coolify-management-validation.md).
