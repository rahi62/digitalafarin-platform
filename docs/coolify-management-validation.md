# Coolify management validation

Validation used Python 3.12, the repository's declared Python dependencies, and
Node 22 for web checks. Coolify request contracts were inspected in the exact
4.3.23 source tag. Tests use HTTP mocks and a temporary Django database; no
production Coolify operation or workload migration was performed.

| Check | Result |
| --- | --- |
| `python apps/api/manage.py test control -v 1` | 156 passed |
| `python apps/api/manage.py check` | Passed |
| `python apps/api/manage.py makemigrations --check --dry-run` | No changes detected |
| `pytest mcp/tests/test_coolify.py -q` | 12 passed |
| `pytest mcp/tests -q` | 45 passed, 1 existing failure (below) |
| `pytest agent/tests -q` outside the restricted sandbox | 188 passed, 32 skipped |
| `npm test` in `apps/web`, Node 22 | 10 passed |
| `npm run lint` in `apps/web`, Node 22 | Passed |
| `npm run build` in `apps/web`, Node 22, CI placeholder API configuration | Passed |
| `PYTHONPATH=.:agent python apps/api/manage.py test acceptance.test_migration_readiness -v 1` | 1 existing error (below) |
| `bash -n infra/bootstrap-platform-upgrade.sh` | Passed |
| `git diff --check` | Passed |

The agent suite initially hit sandbox restrictions on Unix sockets and an async
progress test. A complete rerun outside the sandbox passed. The 32 skips are the
suite's existing gated tests; no tests were marked skipped or weakened here.

## Baseline failures, not hidden

Both remaining failures were reproduced in a separate, untouched checkout of
GitHub `main` at `e9b1739` using the same Python environment:

- MCP `test_create_domain_posts_typed_project_domain_payload`: the existing
  hostname regex rejects `cafeno.digitalafarin.ir`. That code is unchanged by
  this PR. The new MCP CI job deliberately runs the full suite and will expose
  this failure rather than omit or xfail it.
- Acceptance `test_complete_safe_migration_fixture`: the existing fixture calls
  `deploy_release(..., apps_root=...)`, but that function no longer accepts
  `apps_root`. The fixture and deployment engine are unchanged by this PR.

Baseline MCP also had a stale static tool inventory assertion (2 failed,
32 passed in total). Because the Coolify tool inventory is being extended, that
assertion is updated to include all tools already on main plus the new module;
its exact-name and forbidden-name checks remain enforced.

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
production rollout. PR CI status is reported at PR creation; no deployment is
part of this change.
