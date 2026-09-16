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

## 8. Deploy final `main`

After the feature branch and its merge with latest `origin/main` pass the complete
matrix, push the feature branch, integrate it into `main`, push `main`, and deploy
that exact final commit:

```bash
sudo -u deploy -H git -C /opt/digitalafarin-platform fetch --prune origin
sudo -u deploy -H git -C /opt/digitalafarin-platform switch main
sudo -u deploy -H git -C /opt/digitalafarin-platform pull --ff-only origin main

cd /opt/digitalafarin-platform/apps/api
.venv/bin/pip install -r requirements.txt
set -a
. /etc/digitalafarin-platform/api.env
set +a
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py check

# Existing credentials keep their values; update only the two intended principals.
.venv/bin/python manage.py shell -c 'from control.models import ServicePrincipal; scopes=["servers:read","metrics:read","services:read","audit:read","operations:read","operations:create","logs:read"]; names=["chatgpt-vps-mcp","platform-web"]; found=set(ServicePrincipal.objects.filter(name__in=names).values_list("name", flat=True)); assert found == set(names), found; ServicePrincipal.objects.filter(name__in=names).update(scopes=scopes)'

cd /opt/digitalafarin-platform/agent
.venv/bin/pip install -e .

cd /opt/digitalafarin-platform/mcp
.venv/bin/pip install -e .

cd /opt/digitalafarin-platform/apps/web
npm ci
npm run build

sudo install -m 0644 /opt/digitalafarin-platform/infra/systemd/digitalafarin-platform-api.service /etc/systemd/system/
sudo install -m 0644 /opt/digitalafarin-platform/infra/systemd/digitalafarin-platform-web.service /etc/systemd/system/
sudo install -m 0644 /opt/digitalafarin-platform/infra/systemd/digitalafarin-platform-agent.service /etc/systemd/system/
sudo install -m 0644 /opt/digitalafarin-platform/infra/systemd/digitalafarin-platform-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart digitalafarin-platform-api digitalafarin-platform-web digitalafarin-platform-agent digitalafarin-platform-mcp
```

Install but do not enable the committed tunnel unit while the legacy tunnel unit
owns the same profile. That handoff is a separate availability-sensitive change.

## 9. Non-destructive production acceptance

Do not create, deploy, roll back, restore, reload Nginx, issue certificates, or
change DNS merely to prove production. Use reads and health checks:

```bash
sudo -u deploy -H git -C /opt/digitalafarin-platform status --short --branch
sudo -u deploy -H git -C /opt/digitalafarin-platform rev-parse HEAD
systemctl is-active digitalafarin-platform-api digitalafarin-platform-web digitalafarin-platform-agent digitalafarin-platform-mcp
curl -fsS http://127.0.0.1:9750/health/
curl -fsSI http://127.0.0.1:9751/
sudo nginx -t
ss -ltnp | grep -E ':(9743|9750|9751|3060)[[:space:]]'
df -P / /opt /srv
```

Confirm the API reports a fresh, non-stale server snapshot; MCP is reachable at
`http://127.0.0.1:3060/mcp`; the running tunnel process owns the expected profile;
and API/MCP/Admin resource reads contain no credential or secret value.

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
