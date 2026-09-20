# Migration deployment runbook

This is the production procedure for moving a project onto the DigitalAfarin
deployment platform. It preserves the fixed security boundary: the Agent is
outbound-only; API, Web, MCP, and tunnel targets are loopback-only; all mutations
are typed; and secret values must not appear in terminal capture, Git, reports,
screenshots, API responses, MCP output, or tickets.

## 1. Preconditions and stop conditions

Before any mutation, record the intended server, project, services, repositories,
exact branches or commits, volume names, database backup names, domains, and
rollback release. Stop if any target is ambiguous, if the working tree is dirty,
if a required credential is unavailable, or if the operation would overwrite the
only copy of persistent data.

Run these read-only checks on the target:

```bash
sudo -u deploy -H git -C /opt/digitalafarin-platform status --short --branch
df -P / /opt /srv
systemctl is-active digitalafarin-platform-api digitalafarin-platform-web digitalafarin-platform-agent digitalafarin-platform-mcp
ss -ltnp | grep -E ':(9743|9750|9751|3060)[[:space:]]'
```

All four application listeners must be `127.0.0.1`. Disk at `>=80%` requires a
documented cleanup/space plan before migration; `>=90%` stops deployment.

## 2. Install and bootstrap the platform

Install the repository at `/opt/digitalafarin-platform`, dependencies in the
component-local virtual environments, the committed systemd units, and the
root/service-readable files under `/etc/digitalafarin-platform`. Do not put
credentials in unit files.

Before starting the non-root Agent, install the committed tmpfiles rule and create
only the platform-managed root. The Agent remains `digitalafarin-agent`; it is not
made root and `/srv` as a whole is not writable:

```bash
sudo install -D -m 0644 infra/tmpfiles.d/digitalafarin-platform.conf /etc/tmpfiles.d/digitalafarin-platform.conf
sudo systemd-tmpfiles --create /etc/tmpfiles.d/digitalafarin-platform.conf
sudo install -m 0644 infra/systemd/digitalafarin-platform-agent.service /etc/systemd/system/digitalafarin-platform-agent.service
sudo systemctl daemon-reload
namei -l /srv/digitalafarin
```

The expected owner is `digitalafarin-agent:digitalafarin-agent` with mode `0750`.
The unit grants write access only to `/var/lib/digitalafarin-agent` and
`/srv/digitalafarin`; the typed bootstrap operation creates the three child
directories below that root.

Enroll the Agent with a one-time token, confirm a fresh outbound heartbeat, remove
`PLATFORM_ENROLLMENT_TOKEN` from `agent.env`, and restart the Agent. Queue the
typed `server.bootstrap` operation with an empty payload. It checks the supported
OS, memory, disk, Git, Python, Node, PostgreSQL, Nginx, systemd, and creates only:

```text
/srv/digitalafarin/apps
/srv/digitalafarin/volumes
/srv/digitalafarin/backups
```

Run bootstrap twice. The second result must remain `ready` or the same documented
`warning` and must not remove or replace data.

## 3. Provision the deployment encryption key

`PLATFORM_SECRET_KEYS` is a comma-separated Fernet key ring. The first key is the
write key; later keys remain decrypt-only during rotation. Generate the initial
key directly into the API environment file without printing it:

```bash
sudo /opt/digitalafarin-platform/apps/api/.venv/bin/python - <<'PY'
from pathlib import Path
from cryptography.fernet import Fernet

path = Path("/etc/digitalafarin-platform/api.env")
text = path.read_text(encoding="utf-8")
if any(line.startswith("PLATFORM_SECRET_KEYS=") for line in text.splitlines()):
    raise SystemExit("PLATFORM_SECRET_KEYS already exists; refusing to replace it")
with path.open("a", encoding="utf-8") as handle:
    handle.write("\nPLATFORM_SECRET_KEYS=" + Fernet.generate_key().decode("ascii") + "\n")
PY
```

Back up the key through the approved secret-management channel before creating
encrypted resources. Never copy it into this repository or a report. To rotate,
place a newly generated key first and retain the previous key after the comma
until every ciphertext has been re-encrypted and verified; removing the only key
capable of decrypting existing data is unrecoverable.

Keep `/etc/digitalafarin-platform/api.env` owned by `root:deploy` with mode `0640`
so the API service can read it while other users cannot.

Verify configuration without printing the value:

```bash
sudo sh -c 'grep -q "^PLATFORM_SECRET_KEYS=.." /etc/digitalafarin-platform/api.env'
sudo systemctl restart digitalafarin-platform-api
curl -fsS http://127.0.0.1:9750/health/
```

## 4. Restore a project in dependency order

Use the Admin UI or narrow Control API/MCP actions in this order:

1. Create the project and its target services. Validate repository, branch,
   runtime recipe, root directory, port, health check, and target server.
2. Create plain and secret variables at project, service, or environment scope.
   Confirm secret responses contain only metadata and `has_value`.
3. Create managed volumes. Their host paths must be platform-derived below
   `/srv/digitalafarin/volumes/<project>/`; restore file data into those roots and
   verify owner, group, mode, backup policy, and a known sentinel/checksum.
4. Place an approved PostgreSQL custom-format backup below
   `/srv/digitalafarin/backups`. Create the database resource, then queue restore
   using only the managed backup filename. Verify connectivity and resource state;
   never submit SQL text.
5. Deploy the backend from an exact 40-character commit. Confirm clone, build,
   activation, restart, and post-activation health events end in `succeeded`.
6. Deploy the frontend the same way. A branch deploy must record the exact commit
   it resolved before execution.
7. Redeploy the recorded commit to prove repeatability. Roll back to an existing
   successful release to prove rollback does not rebuild.
8. Confirm restored volume data survived deploy, redeploy, rollback, and release
   cleanup.
9. Create domains, validate staged Nginx configuration, install atomically, reload
   with the fixed handler, and enable SSL through the typed Certbot workflow.
10. Run final production-safe checks, then perform DNS cutover as a separate,
    explicitly approved external change.

## 5. Rollback

Application rollback selects a recorded successful release through the typed
rollback action. The Agent atomically switches `current`, restarts the fixed unit,
and verifies health. It does not clone, install, build, alter managed volume data,
or restore a database.

If automatic rollback after a failed new release also fails verification, stop;
do not delete either release. Preserve events/logs, keep persistent roots intact,
and escalate with the exact deployment and release IDs but no secret values.

Platform-code rollback is separate: select a known-good Git commit in
`/opt/digitalafarin-platform`, rebuild the Web app if its source changed, run
migrations only when the target schema is forward-compatible, and restart only
the affected units. Database migration reversal requires a separately reviewed
backup/restore plan; never guess.

## 6. Retention and disk guardrails

The release engine retains five successful inactive releases per service while
also protecting the active and rollback targets. Cleanup operates only below the
service `releases/` directory, ignores symlinks, and never touches `shared`,
`/srv/digitalafarin/volumes`, `/srv/digitalafarin/backups`, or PostgreSQL data.

- `<80%`: deployment admission is ready.
- `>=80%` and `<90%`: deployment is allowed with a warning; investigate and free
  space using reviewed targets.
- `>=90%`: deployment creation is rejected.
- Missing or heartbeat-stale disk telemetry: deployment creation is rejected.

Never run broad recursive deletion against `/srv`, `/opt`, a service root, or a
path derived from unvalidated input. Prefer verified release-retention cleanup.

## 7. Verify a candidate before integration

From the repository root, use the project environments already provisioned for
CI/deployment:

```bash
cd apps/api
.venv/bin/python manage.py test control.tests -v 2
.venv/bin/python manage.py test control.tests.test_service_adoption_migration -v 2
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run

cd ../../agent
.venv/bin/pytest -q

cd ../mcp
.venv/bin/pytest -q

cd ../apps/web
npm test
npm run lint
npm run build

cd ../..
PYTHONPATH=.:agent apps/api/.venv/bin/python apps/api/manage.py test acceptance.test_migration_readiness -v 2
git diff --check
git grep -nE 'shell[[:space:]]*=[[:space:]]*True|os\.system' -- apps agent mcp
git grep -nE 'da_(agent|service|enroll)_[A-Za-z0-9]{8,}\.[A-Za-z0-9_-]{40,}' -- ':!*.md'
```

The two security scans pass when they produce no matches. Validate committed
deployment artifacts on a compatible host:

```bash
systemd-analyze verify infra/systemd/digitalafarin-platform-*.service
sudo nginx -t
sudo -u digitalafarin-mcp -H sh -c 'set -a; . /home/digitalafarin-mcp/.config/tunnel-client/digitalafarin-vps.env; exec tunnel-client doctor --profile digitalafarin-vps --explain'
```

`doctor` opens a temporary health listener. If the real tunnel is already running,
an `address already in use` result is expected from that isolated diagnostic;
verify the owning process and the live service instead of starting a duplicate.
Production may still use the legacy `digitalafarin-vps-tunnel.service`; do not
enable `digitalafarin-platform-mcp-tunnel.service` until a reviewed handoff stops
the legacy unit and proves the new unit uses the same profile and environment.

## 8. Deploy final `main` — Stage B2 order

Stage B2 is metadata-only adoption. It must not restart an adopted workload,
rewrite a unit, or enable deployment management. Use this order exactly:

1. Confirm production repo is clean and record current SHA.
2. Take/verify the normal database backup/rollback readiness.
3. Pull the reviewed `main` commit.
4. Install API dependencies and run `manage.py migrate --noinput`.
5. Run `manage.py check`.
6. Install the MCP package update.
7. Build the Web app.
8. Restart only `digitalafarin-platform-api`, `digitalafarin-platform-web`, and
   `digitalafarin-platform-mcp` as needed to load Stage B2 code.
9. Do not restart adopted workload units and do not restart the Agent solely for
   Stage B2.
10. Verify existing managed Services remain `managed` with their backfilled unit names.
11. Adopt one protected `digitalafarin-platform-*.service` into the
    `DigitalAfarin Platform` Project.
12. Compare Operation count before/after adoption and require no increase caused by adoption.
13. Verify the Project/Service UI shows lifecycle, protected state, and live inventory state.
14. Verify deploy on the adopted service returns `service_not_managed` and creates
    no Deployment/Operation.
15. Optionally configure deployment metadata; verify state becomes `configured`
    and deploy remains blocked.
16. Only after acceptance, adopt Oily services one at a time; do not perform
    takeover in Stage B2.

Reference rollout commands:

```bash
REPO=/opt/digitalafarin-platform
OLD_SHA="$(sudo -u deploy -H git -C "$REPO" rev-parse HEAD)"
sudo -u deploy -H git -C "$REPO" status --short --branch
test -z "$(sudo -u deploy -H git -C "$REPO" status --porcelain)"

# Verify the normal database backup/rollback readiness here before pulling.

sudo -u deploy -H git -C "$REPO" fetch --prune origin
sudo -u deploy -H git -C "$REPO" switch main
sudo -u deploy -H git -C "$REPO" pull --ff-only origin main
NEW_SHA="$(sudo -u deploy -H git -C "$REPO" rev-parse HEAD)"

cd "$REPO/apps/api"
.venv/bin/pip install -r requirements.txt
set -a
. /etc/digitalafarin-platform/api.env
set +a
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py check

cd "$REPO/mcp"
.venv/bin/pip install -e .

cd "$REPO/apps/web"
npm ci
npm run build

sudo systemctl restart \
  digitalafarin-platform-api \
  digitalafarin-platform-web \
  digitalafarin-platform-mcp

printf 'OLD_SHA=%s\nNEW_SHA=%s\n' "$OLD_SHA" "$NEW_SHA"
```

The Agent package and `digitalafarin-platform-agent.service` are unchanged by
Stage B2. Do not restart them merely for this release. The tunnel handoff remains
a separate availability-sensitive change.

## 9. Non-destructive production acceptance

Do not create, deploy, roll back, restore, reload Nginx, issue certificates, or
change DNS merely to prove production. Use reads and health checks:

```bash
sudo -u deploy -H git -C /opt/digitalafarin-platform status --short --branch
sudo -u deploy -H git -C /opt/digitalafarin-platform rev-parse HEAD
systemctl is-active digitalafarin-platform-api digitalafarin-platform-web digitalafarin-platform-agent digitalafarin-platform-mcp
curl -fsS http://127.0.0.1:9750/health/
for attempt in $(seq 1 30); do
  if curl -fsSI http://127.0.0.1:9751/ >/dev/null; then
    echo "Web ready"
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "Web failed readiness window" >&2
    exit 1
  fi
  sleep 1
done
sudo nginx -t
ss -ltnp | grep -E ':(9743|9750|9751|3060)[[:space:]]'
df -P / /opt /srv
```

Confirm the API reports a fresh, non-stale server snapshot; MCP is reachable at
`http://127.0.0.1:3060/mcp`; the running tunnel process owns the expected profile;
and API/MCP/Admin resource reads contain no credential or secret value.

For the first Stage B2 acceptance, use a protected Platform unit so the binding can
be observed without opening mutation authority. Record Operation count, adopt the
unit as metadata only, then require the count to remain unchanged. Confirm the
Service shows `adopted`, `protected=true`, and current inventory state. A deploy
request must return `409 service_not_managed` before any Deployment or Operation
is created. If deployment metadata is configured, the state becomes `configured`
and deploy remains blocked. There is no `configured -> managed` action in Stage B2.

## 10. The 18 readiness checks

The disposable acceptance fixture proves, in order: (1) enrollment, (2) fresh
heartbeat plus idempotent bootstrap, (3) project creation, (4) service creation,
(5) plain variable creation, (6) secret variable metadata without disclosure,
(7) managed volume creation, (8) exact-commit checkout, (9) build, (10) health
verification, (11) atomic activation, (12) repeatable redeploy, (13) rollback
without rebuild, (14) volume persistence, (15) managed PostgreSQL restore,
(16) bounded log retrieval, (17) secret redaction, and (18) both disk thresholds.

Run it twice locally. Production evidence is read-only unless the exact mutation
has separately been approved and demonstrated safe.
