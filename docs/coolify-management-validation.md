# Coolify management validation

Validation used Python 3.12, the repository's declared Python dependencies, and
Node 22 for web checks. Coolify request contracts were inspected in the exact
4.3.23 source tag. Tests use HTTP mocks and a temporary Django database; no
production Coolify operation or workload migration was performed.

| Check | Result |
| --- | --- |
| `PYTHONPATH=.:agent python apps/api/manage.py test control acceptance.test_migration_readiness -v 1` | 159 passed; also passed in a clean API-only dependency environment |
| `python apps/api/manage.py check` | Passed |
| `python apps/api/manage.py makemigrations --check --dry-run` | No changes detected |
| `PYTHONPATH=mcp:agent pytest mcp/tests -q` | 66 passed |
| `PYTHONPATH=mcp:agent pytest agent/tests -q` outside the restricted sandbox | 188 passed, 32 existing gated skips |
| `npm test` in `apps/web`, Node 22 | 31 passed |
| `npm run lint` in `apps/web`, Node 22 | Passed |
| `npm run build` in `apps/web`, Node 22, CI placeholder API configuration | Passed |
| `bash -n infra/bootstrap-platform-upgrade.sh` | Passed |
| `git diff --check` | Passed |

No failures were suppressed, skipped, or marked xfail by this PR. The agent skips
are the existing ownership/integration gates. No production operation was run.
The Platform CI API job now includes the migration acceptance fixture and Node 22;
acceptance changes also trigger the workflow.

## Investigated and fixed baseline failures

The actual failed GitHub Actions MCP job was
[112348277047](https://github.com/rahi62/digitalafarin-platform/actions/runs/37486648194/job/112348277047).
It reported `test_create_domain_posts_typed_project_domain_payload` failing because
the hostname regex rejected `cafeno.digitalafarin.ir` (45 passed, 1 failed).
Freshly fetched `origin/main` remained at `e9b1739`. In an untouched isolated
checkout with imports explicitly bound to that checkout, the complete Control
Plane client test file reproduced this exact failure (17 passed, 1 failed).
The legacy acceptance fixture independently reproduced the obsolete `apps_root`
keyword error there.

The hostname fix changes only the incorrectly escaped dot separator. New
regressions failed before the fix and pass afterward. They cover valid DNS names,
63-character labels and a 253-character hostname, and reject oversized names,
backslashes, empty labels, leading/trailing hyphens, URLs, ports, paths, whitespace,
and command punctuation before any HTTP request. Validation was not weakened.

The acceptance fixture now calls `deploy_release` and `rollback_release` with the
current `helper` interface. A disposable helper double builds real local Git
checkouts with Node and switches temporary release symlinks. Assertions cover
both build artifacts, the exact commit, deploy/redeploy/rollback results, helper
identity, pruning, and the persistent sentinel. Unsupported managed environment
and volume payloads are explicitly rejected before preparation. Production
deployment code is unchanged. This fixture does not validate privileged helper
ownership/sealing/systemd; those remain the agent suite's responsibility.

## Security and compatibility re-review

All 16 new management tools (including their read operations) were re-reviewed
through MCP, Django routing/authentication, serializers, policy, and upstream client.
An independent code review found no blocking security issue. Additional tests
exercise the exact required scope on all 16 routes and cross-principal/deleted
ownership denial on all 13 application-bound routes before upstream resource calls.

| Concern | Verified boundary |
| --- | --- |
| Authorization | Explicit read/manage/deploy/delete scopes; active, unrevoked service identity; administrator target policy |
| Destructive operations | Stop requires deploy scope; delete requires separate delete scope plus exact UUID confirmation; cleanup flags preserve volumes/networks/configurations |
| Secrets | Write-only env values; no payloads in audits; projected responses; exact allowlisted lifecycle logs only; generic errors |
| Endpoint/command injection | Fixed routes and verbs, bounded identifiers, strict unknown-field rejection, no raw command/Compose/Dockerfile fields; reserved build-control variables rejected |
| Ownership | Principal-owned managed registry; deleted/unmanaged/other-principal denial; repository and environment/server drift checks; deployment application-ID verification |
| Compatibility | Existing four inventory tools/routes retained; complete MCP/API/agent/web suites green; production deployment contract unchanged |

Approved repository maintainers and server-side administrator policy remain trusted
inputs. Review and mocked tests do not replace disposable live Coolify staging
validation before a future rollout.

## New coverage

API/client tests verify fixed upstream routes and verbs, placement selection,
public/private GitHub creation, duplicate/uncertain create rejection, explicit
scopes and deletion confirmation, missing/invalid/revoked credentials, disabled
principals, cross-principal denial, unmanaged/protected resources, policy and
placement drift, GitHub slug normalization, validation and unknown-field
rejection, bounded ports/paths/URLs/variables/logs, literal build/runtime
variables, metadata-only reads, safe audit content, deployment ownership,
redaction, invalid upstream JSON/shapes, network/API failures, oversized
responses, redirect rejection, and non-destructive cleanup flags.

MCP tests verify every new tool's typed mapping, Control Plane-only traffic,
identifier validation, log bounds, forbidden execution fields, secret-safe
validation errors, environment value transmission without response echo, and
sanitized authorization/upstream failures.

This is mocked contract validation, not a live staging acceptance claim. A
separate disposable Coolify 4.3.23 environment must be used before a later
production rollout. Current GitHub CI results are recorded in PR #33; no deployment is part of this change.
