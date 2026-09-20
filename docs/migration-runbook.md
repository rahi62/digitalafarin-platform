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

## 10. Stage B3 — Controlled Takeover

Stage B3 turns one already `configured · unmanaged` service into a health-verified
managed immutable release. The first candidate is **DigitalAfarin Platform Web**
only. Oily is explicitly excluded from the first Stage B3 takeover.

Production reference paths and listeners:

```text
Repo:    /opt/digitalafarin-platform
API:     127.0.0.1:9750
Web:     127.0.0.1:9751
MCP:     127.0.0.1:3060
Web env: /etc/digitalafarin-platform/web.env
```

### A. Deploy Stage B3 code before any takeover

1. Confirm the production repo is clean and record the old SHA.
2. Fetch and fast-forward only to the reviewed Stage B3 `main` SHA.
3. Build Web as `deploy`; do not leave root-owned `.next`/`node_modules` artifacts.
4. Apply the Stage B3 migration and run `manage.py check`.
5. Install updated MCP and Agent packages.
6. Install and enable `digitalafarin-platform-takeover-helper.service`. The helper runs as root, has no network listener, accepts only a local Unix-socket peer authenticated as `digitalafarin-agent`, and allowlists only the exact first-candidate systemd unit.
7. Restart only Platform API/MCP/Web/Agent units whose code/package changed.
8. Verify API, Web, MCP, Agent, takeover helper, Nginx, loopback listeners, fresh heartbeat, and disk guardrails.
9. Verify the Agent advertises `takeover_helper_v1` before creating a takeover.
10. Verify takeover API/MCP discovery before creating a takeover.
11. Do **not** reuse the old Stage B2 SHA `6b4c43f...` as the takeover target. Use the exact
   Stage B3 commit already running in production.

### B. PREPARE `platform-web` without mutation

Queue PREPARE using the exact Stage B3 production commit. Require all of the following
before offering ACTIVATE:

```text
takeover.state == prepared
service.lifecycle_state == configured
source snapshot persisted
source fingerprint persisted
release exists under /srv/digitalafarin/apps/.../releases/<name>
WorkingDirectory still /opt/digitalafarin-platform/apps/web
90-digitalafarin-managed.conf does not exist
platform-web MainPID/start time did not change because of PREPARE
```

PREPARE is a hard non-mutation boundary: no `current` activation, no managed drop-in,
no `daemon-reload`, and no workload restart.

For private repositories, the privileged helper does not receive Git credentials from the
Control Plane and does not expose deploy-user SSH material to build scripts. Each allowlisted
takeover binding must map to a root-configured trusted local source repository through
`DIGITALAFARIN_TAKEOVER_SOURCE_REPOSITORIES`. The first production mapping is:

The helper does not drop privileges in-process. It asks systemd PID 1 to create a
collected, hardened transient one-shot worker as the validated service `User` and
`Group`. `PrivateUsers=yes` prevents deploy's host `sudo` and `users` supplementary
groups from being mapped into the worker. Trusted-source Git verification has no writable path. Git release preparation,
`npm ci`, and `npm run build` receive only the exact allocated release directory through
`ReadWritePaths`. Worker unit names and commands are generated only by trusted helper
code; they are not protocol fields.


```text
digitalafarin-platform|platform-web|digitalafarin-platform-web.service|/opt/digitalafarin-platform
```

The helper verifies that the trusted local repository `HEAD` exactly matches the requested
production commit before allocating a release. The caller-supplied repository value remains
credential-free HTTPS metadata and is never used as the authenticated clone source.

### C. ACTIVATE `platform-web`

Before activation, the Agent re-inspects the effective systemd source and must reject
`service_configuration_changed` if the prepared fingerprint no longer matches.
ACTIVATE then switches `current`, installs the single managed drop-in, reloads systemd,
restarts the exact configured unit, and requires two consecutive successful loopback
health responses.

After success verify:

```bash
systemctl show digitalafarin-platform-web.service \
  -p User \
  -p Group \
  -p WorkingDirectory \
  -p ExecStart \
  -p EnvironmentFiles

curl -fsSI http://127.0.0.1:9751/
```

Expected invariants:

```text
lifecycle_state == managed
WorkingDirectory=/srv/digitalafarin/apps/digitalafarin-platform/platform-web/current/apps/web
User=deploy
Group=www-data
EnvironmentFile=/etc/digitalafarin-platform/web.env
ExecStart=/usr/bin/npm start -- --hostname 127.0.0.1 --port 9751
```

Also verify one successful takeover Release exists, takeover audit events are present,
and generic start/stop/restart remains blocked for the protected
`digitalafarin-platform-web.service`.

### D. Failure acceptance and automatic rollback

If the new release fails health verification and rollback succeeds, require:

```text
Service remains configured
Takeover is rolled_back
managed drop-in is absent
first-takeover current link is restored to its previous state (normally absent)
base unit again supplies /opt/digitalafarin-platform/apps/web
original loopback Web health passes
no takeover Release is marked active
```

Do not convert the Service to `managed` after any failed/rolled-back activation.

### E. `rollback_failed`

If automatic rollback cannot restore healthy service:

1. Service remains `configured`.
2. Stop automated deploy/takeover actions for that Service.
3. Preserve the prepared release and takeover metadata for forensics.
4. Inspect takeover, Operation, audit events, base/drop-in state, `current`, and the
   systemd journal manually.
5. Do not retry takeover until the source service is healthy and the inconsistency has
   been understood.

### F. First-candidate isolation

The first Stage B3 production acceptance mutates only
`digitalafarin-platform-web.service`. Before and after ACTIVATE, record states for Oily
and KhoshVisa units and require no restart/start-time change caused by takeover. Oily
is not a Stage B3 first-candidate even if it is already visible in inventory.


### G. Stage B3.1 privileged helper boundary

The host Agent remains `User=digitalafarin-agent` with `NoNewPrivileges=yes`. It must
not receive sudo rights and must not be changed to root. Operations requiring root
ownership, `runuser`, writes below `/etc/systemd/system`, `daemon-reload`, or restart
of the dedicated takeover unit are delegated to:

```text
digitalafarin-platform-takeover-helper.service
/run/digitalafarin-takeover/helper.sock
```

The helper is intentionally local-only. It has no TCP listener and accepts a small
versioned JSON protocol over the Unix socket. The server authenticates the peer UID
and the socket is mode `0660`, owned by `root:digitalafarin-agent`. The helper exposes
only these fixed operations:

```text
prepare_node_nextjs_release
activate_release
rollback_activation
cleanup_release
```

It does not expose arbitrary shell execution, arbitrary filesystem paths, or arbitrary
systemd unit names. The production systemd unit sets:

```text
DIGITALAFARIN_TAKEOVER_ALLOWED_UNITS=digitalafarin-platform-web.service
```

PREPARE delegates release allocation, exact-commit Git checkout, the derived Next.js
build recipe, ownership, sealing, and writable `.next/cache` setup to the helper.
ACTIVATE rechecks the source fingerprint inside the privileged helper immediately
before mutation, then changes only the derived `current` symlink and reserved managed
drop-in. Health verification remains in the non-root Agent. If health fails, the Agent
requests the fixed rollback operation and verifies health again.

The failed pre-B3.1 takeover record should remain in the audit history. Do not reuse or
edit that row; create a new takeover after the helper is deployed and verified.

### H. Stage B3.5 preallocated-release rollout and PREPARE gate

Set `MERGED_SHA` to the reviewed 40-character merge commit on `main`. This rollout
restarts only the takeover Helper and Agent before PREPARE. It does not restart Web,
change Web's working directory, create `current`, install the managed drop-in, or
activate the takeover.

```bash
set -eu
cd /opt/digitalafarin-platform
MERGED_SHA='<MERGED_MAIN_SHA>'
test "${#MERGED_SHA}" -eq 40

test "$(systemctl is-active digitalafarin-platform-web.service)" = active
test "$(systemctl show digitalafarin-platform-web.service -p User --value)" = deploy
test "$(systemctl show digitalafarin-platform-web.service -p Group --value)" = www-data
test "$(systemctl show digitalafarin-platform-web.service -p WorkingDirectory --value)" = /opt/digitalafarin-platform/apps/web
test ! -e /srv/digitalafarin/apps/digitalafarin-platform/platform-web/current
test ! -L /srv/digitalafarin/apps/digitalafarin-platform/platform-web/current
test ! -e /etc/systemd/system/digitalafarin-platform-web.service.d/90-digitalafarin-managed.conf

set -a
. /etc/digitalafarin-platform/api.env
set +a
API_PY=/opt/digitalafarin-platform/apps/api/.venv/bin/python
API_DIR=/opt/digitalafarin-platform/apps/api
test "$($API_PY "$API_DIR/manage.py" shell -c \
  "from control.models import Service; s=Service.objects.get(project__slug='digitalafarin-platform', name='platform-web', unit_name='digitalafarin-platform-web.service'); print(f'{s.lifecycle_state}|{s.target_server.status}')")" = 'configured|online'

WEB_PID_BEFORE=$(systemctl show digitalafarin-platform-web.service -p MainPID --value)
WEB_STARTED_BEFORE=$(systemctl show digitalafarin-platform-web.service -p ActiveEnterTimestampMonotonic --value)

git fetch --prune origin main
test "$(git branch --show-current)" = main
test "$(git rev-parse origin/main)" = "$MERGED_SHA"
git merge --ff-only "$MERGED_SHA"
test "$(git rev-parse HEAD)" = "$MERGED_SHA"

install -o root -g root -m 0644 \
  infra/tmpfiles.d/digitalafarin-platform.conf \
  /etc/tmpfiles.d/digitalafarin-platform.conf
systemd-tmpfiles --create /etc/tmpfiles.d/digitalafarin-platform.conf
chmod 0751 /srv/digitalafarin /srv/digitalafarin/apps
test "$(stat -c %a /srv/digitalafarin)" = 751
test "$(stat -c %a /srv/digitalafarin/apps)" = 751
test "$(stat -c %a /srv/digitalafarin/apps/digitalafarin-platform/platform-web/releases)" = 755

agent/.venv/bin/pip install ./agent
test "$(agent/.venv/bin/python -c 'import digitalafarin_agent; print(digitalafarin_agent.__version__)')" = 0.2.5
install -o root -g root -m 0644 \
  infra/systemd/digitalafarin-platform-takeover-helper.service \
  /etc/systemd/system/digitalafarin-platform-takeover-helper.service
systemctl daemon-reload
systemctl restart digitalafarin-platform-takeover-helper.service
systemctl restart digitalafarin-platform-agent.service
systemctl is-active --quiet digitalafarin-platform-takeover-helper.service
systemctl is-active --quiet digitalafarin-platform-agent.service

agent/tests/integration/run_systemd_worker_integration.sh \
  /opt/digitalafarin-platform deploy www-data

cd "$API_DIR"

for attempt in $(seq 1 24); do
  HEARTBEAT=$($API_PY manage.py shell -c \
    "from control.models import Server; s=Server.objects.get(name='DigitalAfarin-Primary'); print(s.agent_version+'|'+s.status+'|'+str('takeover_helper_v1' in s.capabilities))")
  test "$HEARTBEAT" = '0.2.5|online|True' && break
  test "$attempt" -lt 24
  sleep 5
done

test "$(systemctl show digitalafarin-platform-web.service -p MainPID --value)" = "$WEB_PID_BEFORE"
test "$(systemctl show digitalafarin-platform-web.service -p ActiveEnterTimestampMonotonic --value)" = "$WEB_STARTED_BEFORE"
test "$(systemctl show digitalafarin-platform-web.service -p WorkingDirectory --value)" = /opt/digitalafarin-platform/apps/web

TAKEOVER_ID=$($API_PY manage.py shell -c \
  "from control.models import Service; from control.services.takeovers import queue_takeover_prepare; s=Service.objects.get(project__slug='digitalafarin-platform', name='platform-web', unit_name='digitalafarin-platform-web.service'); t,_=queue_takeover_prepare(service=s, exact_commit='$MERGED_SHA', requested_by='stage-b3.5-rollout'); print(t.public_id)")
test -n "$TAKEOVER_ID"

for attempt in $(seq 1 180); do
  TAKEOVER_STATE=$($API_PY manage.py shell -c \
    "from control.models import ServiceTakeover; print(ServiceTakeover.objects.get(public_id='$TAKEOVER_ID').state)")
  case "$TAKEOVER_STATE" in
    prepared) break ;;
    failed|rolled_back|rollback_failed|canceled) exit 1 ;;
  esac
  test "$attempt" -lt 180
  sleep 5
done

RELEASE_PATH=$($API_PY manage.py shell -c \
  "import re; from pathlib import Path; from control.models import ServiceTakeover; t=ServiceTakeover.objects.select_related('service').get(public_id='$TAKEOVER_ID'); assert t.state == 'prepared'; assert t.service.lifecycle_state == 'configured'; assert t.requested_commit == '$MERGED_SHA'; assert t.resolved_commit == '$MERGED_SHA'; assert isinstance(t.source_snapshot, dict) and t.source_snapshot; assert re.fullmatch(r'[0-9a-f]{64}', t.source_fingerprint); p=Path(t.release_path); expected=Path('/srv/digitalafarin/apps/digitalafarin-platform/platform-web/releases') / t.release_name; assert p == expected; print(p)")

test -f "$RELEASE_PATH/apps/web/package.json"
test -f "$RELEASE_PATH/apps/web/package-lock.json"
test -d "$RELEASE_PATH/apps/web/.next"
test ! -e /srv/digitalafarin/apps/digitalafarin-platform/platform-web/current
test ! -L /srv/digitalafarin/apps/digitalafarin-platform/platform-web/current
test ! -e /etc/systemd/system/digitalafarin-platform-web.service.d/90-digitalafarin-managed.conf
test "$(systemctl show digitalafarin-platform-web.service -p MainPID --value)" = "$WEB_PID_BEFORE"
test "$(systemctl show digitalafarin-platform-web.service -p ActiveEnterTimestampMonotonic --value)" = "$WEB_STARTED_BEFORE"
test "$(systemctl show digitalafarin-platform-web.service -p WorkingDirectory --value)" = /opt/digitalafarin-platform/apps/web
```

Stop here. Preserve all earlier failed takeover rows for audit. ACTIVATE remains a
separate explicit production gate and must not be queued as part of this rollout.

## 11. The 18 readiness checks

The disposable acceptance fixture proves, in order: (1) enrollment, (2) fresh
heartbeat plus idempotent bootstrap, (3) project creation, (4) service creation,
(5) plain variable creation, (6) secret variable metadata without disclosure,
(7) managed volume creation, (8) exact-commit checkout, (9) build, (10) health
verification, (11) atomic activation, (12) repeatable redeploy, (13) rollback
without rebuild, (14) volume persistence, (15) managed PostgreSQL restore,
(16) bounded log retrieval, (17) secret redaction, and (18) both disk thresholds.

Run it twice locally. Production evidence is read-only unless the exact mutation
has separately been approved and demonstrated safe.
