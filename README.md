# DigitalAfarin Platform

Internal VPS control plane for DigitalAfarin. The platform combines outbound-only host agents, a scoped Django control plane, a localhost-only MCP server, and a migration deployment engine for typed bootstrap, persistent resources, exact-commit releases, health verification, and rollback.

## Architecture

```text
ChatGPT
   |
   v
OpenAI Secure MCP Tunnel
   |
   v
DigitalAfarin VPS MCP (127.0.0.1:3060/mcp)
   |
   v
Django Control Plane
   ^
   |
   +---- HTTPS outbound heartbeat ---- Host Agent: Primary VPS
   +---- HTTPS outbound heartbeat ---- Host Agent: VPS #2
   +---- HTTPS outbound heartbeat ---- Host Agent: VPS #3
```

The browser and ChatGPT never receive agent credentials. The MCP does not contact host agents or PostgreSQL directly. Each VPS has an independent, revocable agent credential, and the MCP has its own scoped operator service-principal credential for inventory reads and typed operations.

## Current capabilities

- Multi-server UUID identity with one optional active default server
- CPU, memory, disk and uptime snapshots
- Allow-listed systemd service discovery
- One-time agent enrollment with per-server credentials
- Outbound agent heartbeat ingestion
- Stale/offline detection from heartbeat freshness
- Scoped Control Plane API for inventory reads and typed operations
- MCP tools for inventory plus narrow service/deployment operations
- Legacy single-server pull/manual sync kept temporarily for migration compatibility
- UUID-backed projects, Systemd services, health checks, deployments, and immutable releases
- Authenticated encryption for deployment secrets with metadata-only API, MCP, and UI responses
- Typed, idempotent server bootstrap and structured readiness results
- Persistent managed volumes under `/srv/digitalafarin/volumes`
- Managed PostgreSQL resources and restore from `/srv/digitalafarin/backups`
- Exact-commit deployments under `/srv/digitalafarin/apps`, atomic activation, health verification, and rollback without rebuild
- Five total managed releases retained, including active/rollback releases; protected releases and persistent roots are never removed to satisfy the budget
- Typed domain/Nginx/Certbot workflows with validate-before-install behavior
- Migration readiness UI backed by current operations, deployments, resources, and disk telemetry

The operation foundation supports audited, typed requests for bounded service
control/logs, bootstrap, volumes, database create/restore, exact-commit deploy and
rollback, and domain/SSL configuration. Agents claim and execute these operations
outbound; no inbound Agent management port or arbitrary command interface exists.

Operation-capable service principals use independent scopes in addition to the
four inventory-read scopes:

```text
operations:read
operations:create
logs:read
```

All `digitalafarin-platform-*`, MCP, tunnel, and platform-management units are
protected from mutation even when their names match a discovery allow-list.

## Local development

### 1. Django API

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DJANGO_SECRET_KEY=dev-secret
export PLATFORM_API_TOKEN=dev-api-token
export PLATFORM_SECRET_KEYS="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

### 2. Host Agent — outbound mode

Generate an enrollment token in the Django project first:

```bash
cd apps/api
source .venv/bin/activate
python manage.py create_enrollment_token --minutes 15 --created-by local-dev
```

Then start the agent with the one-time enrollment value:

```bash
cd ../../agent
python -m venv .venv
source .venv/bin/activate
pip install -e .
export PLATFORM_CONTROL_URL=http://127.0.0.1:8000
export PLATFORM_ENROLLMENT_TOKEN='<one-time token>'
export AGENT_TOKEN_PATH="$PWD/.dev-agent-token"
export AGENT_SERVICE_PREFIXES=ssh,nginx,digitalafarin-
uvicorn digitalafarin_agent.main:app --host 127.0.0.1 --port 9743 --reload
```

After first enrollment, remove `PLATFORM_ENROLLMENT_TOKEN`; the persistent agent token is read from `AGENT_TOKEN_PATH`.

### 3. MCP

Create the MCP operator principal once in Django:

```bash
cd apps/api
source .venv/bin/activate
python manage.py create_service_principal chatgpt-vps-mcp --profile operator
```

Use the one-time printed value only as the MCP process environment:

```bash
cd ../../mcp
python -m venv .venv
source .venv/bin/activate
pip install -e .
export CONTROL_PLANE_URL=http://127.0.0.1:8000
export CONTROL_PLANE_TOKEN='<service-principal token>'
export MCP_HOST=127.0.0.1
export MCP_PORT=3060
export MCP_PATH=/mcp
python -m digitalafarin_vps_mcp.server
```

The MCP endpoint is `http://127.0.0.1:3060/mcp`.

### 4. Next.js admin

The admin UI uses the UUID-based Control Plane API and keeps its credential on the Next.js server runtime. Create a separate operator principal for the web app rather than reusing the ChatGPT MCP credential:

```bash
cd apps/api
source .venv/bin/activate
python manage.py create_service_principal platform-web --profile operator
```

Store the one-time credential outside Git, then run the web app:

```bash
cd ../../apps/web
npm install
export PLATFORM_API_URL=http://127.0.0.1:8000
export PLATFORM_API_TOKEN='<platform-web service credential>'
npm run dev
```

The browser never receives `PLATFORM_API_TOKEN`; Server Components call `/api/control/v1/*` directly.

## Production bootstrap: first VPS + MCP

For the complete migration, restore, deployment, rollback, retention, disk, and production-safe acceptance procedure, follow [`docs/migration-runbook.md`](docs/migration-runbook.md). The runbook is authoritative for Stage B and includes encryption-key provisioning without disclosing key material.

Install the repository under `/opt/digitalafarin-platform`, create the service accounts used by the committed systemd units, create `/etc/digitalafarin-platform`, and install the API, Agent and MCP dependencies into their local `.venv` directories. Keep real credentials only in root/service-readable environment files, never in Git.

Before starting the Agent, install `infra/tmpfiles.d/digitalafarin-platform.conf` into `/etc/tmpfiles.d/`, run `systemd-tmpfiles --create` for that file, and install the current Agent unit. This pre-creates only `/srv/digitalafarin` as `digitalafarin-agent:digitalafarin-agent` mode `0750`; the Agent remains non-root and its systemd write boundary is limited to that root plus `/var/lib/digitalafarin-agent`.

### 1. Migrate Django and create the one-time enrollment credential

```bash
cd /opt/digitalafarin-platform/apps/api
source .venv/bin/activate
set -a
source /etc/digitalafarin-platform/api.env
set +a
python manage.py migrate
python manage.py create_enrollment_token --minutes 15 --created-by rahi
```

Copy that command's one-time output into `/etc/digitalafarin-platform/agent.env` as:

```dotenv
PLATFORM_CONTROL_URL=https://<your-control-plane-host>
PLATFORM_ENROLLMENT_TOKEN=<one-time enrollment credential>
AGENT_TOKEN_PATH=/var/lib/digitalafarin-agent/agent.token
AGENT_HEARTBEAT_INTERVAL_SECONDS=15
AGENT_NAME=DigitalAfarin-Primary
AGENT_SERVICE_PREFIXES=digitalafarin-,oily-,khoshvisa-
```

Start/restart the agent and inspect only sanitized logs:

```bash
sudo systemctl restart digitalafarin-platform-agent
sudo journalctl -u digitalafarin-platform-agent -n 100 --no-pager
```

After the first successful enrollment, immediately remove the one-time enrollment credential and restart the agent:

```bash
sudo sed -i '/^PLATFORM_ENROLLMENT_TOKEN=/d' /etc/digitalafarin-platform/agent.env
sudo systemctl restart digitalafarin-platform-agent
```

The Agent writes its independent long-lived credential to `/var/lib/digitalafarin-agent/agent.token` with mode `0600`.

### 2. Select the default VPS

For the first enrolled server:

```bash
cd /opt/digitalafarin-platform/apps/api
source .venv/bin/activate
python manage.py shell -c 'from control.models import Server; s=Server.objects.order_by("created_at").first(); Server.objects.update(is_default=False); s.is_default=True; s.save(update_fields=["is_default"]); print(s.public_id)'
```

For later servers, select the intended row by `public_id` instead of relying on creation order.

### 3. Create the MCP operator identity

```bash
python manage.py create_service_principal chatgpt-vps-mcp --profile operator
```

Copy the one-time printed service credential into `/etc/digitalafarin-platform/mcp.env`:

```dotenv
CONTROL_PLANE_URL=http://127.0.0.1:9750
CONTROL_PLANE_TOKEN=<operator service-principal credential>
MCP_HOST=127.0.0.1
MCP_PORT=3060
MCP_PATH=/mcp
```

Do **not** paste enrollment credentials, agent credentials or MCP service credentials into ChatGPT, issue trackers, Git commits, screenshots or logs.

### 4. Configure the admin web operator identity

Create a dedicated operator identity for the Next.js panel:

```bash
cd /opt/digitalafarin-platform/apps/api
source .venv/bin/activate
python manage.py create_service_principal platform-web --profile operator
```

Write the one-time credential to `/etc/digitalafarin-platform/web.env` without printing it into logs or shell history:

```dotenv
PLATFORM_API_URL=http://127.0.0.1:9750
PLATFORM_API_TOKEN=<platform-web service-principal credential>
```

The committed web unit listens only on `127.0.0.1:9751`. Build before starting it:

```bash
cd /opt/digitalafarin-platform/apps/web
npm ci || npm install
npm run test
npm run lint
npm run build
sudo systemctl enable --now digitalafarin-platform-web
```

Do not expose port `9751` directly to the Internet. Publish it only through the HTTPS Nginx virtual host. The Phase 1 panel has no application-level login yet, so the Nginx vhost must require HTTP Basic Authentication using a root-managed htpasswd file (for example `/etc/nginx/.htpasswd-digitalafarin-platform`).

For `platform.digitalafarin.ir`, point DNS to the VPS before enabling the public vhost, then create the Basic Auth file interactively so the password is not stored in shell history:

```bash
sudo apt-get install -y apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd-digitalafarin-platform rahi
sudo chmod 640 /etc/nginx/.htpasswd-digitalafarin-platform
sudo chown root:www-data /etc/nginx/.htpasswd-digitalafarin-platform
```

Install the HTTP vhost, validate Nginx, obtain the certificate with Certbot, and only then enable the HTTPS server block from `infra/nginx/platform.conf.example`. DNS changes and certificate issuance are production publication steps and must not be guessed or performed against an unrelated hostname.

### 5. Start MCP and install the replacement Secure MCP Tunnel unit

Before enabling the tunnel service, verify the actual binary location:

```bash
command -v tunnel-client
```

The committed unit assumes `/usr/local/bin/tunnel-client`. If the command above returns another path, edit only `ExecStart` in `digitalafarin-platform-mcp-tunnel.service` during deployment.

The tunnel unit runs as `digitalafarin-mcp`, so verify the profile is readable by that same service account before its reviewed handoff:

```bash
sudo -u digitalafarin-mcp tunnel-client doctor --profile digitalafarin-vps --explain
```

If the profile was initialized under another Unix account, configure the `digitalafarin-vps` profile for `digitalafarin-mcp` rather than copying a private credential into Git or the unit file.

Install the committed replacement tunnel unit, but start only the application
units during this step:

```bash
sudo install -m 0644 \
  /opt/digitalafarin-platform/infra/systemd/digitalafarin-platform-mcp-tunnel.service \
  /etc/systemd/system/digitalafarin-platform-mcp-tunnel.service
sudo systemctl daemon-reload
sudo systemctl enable --now digitalafarin-platform-api
sudo systemctl enable --now digitalafarin-platform-agent
sudo systemctl enable --now digitalafarin-platform-mcp
```

Do **not** enable or start `digitalafarin-platform-mcp-tunnel.service` while
`digitalafarin-vps-tunnel.service` owns the `digitalafarin-vps` profile. Perform
the reviewed handoff in [`docs/migration-runbook.md`](docs/migration-runbook.md):
stop the legacy unit, prove the replacement uses the same profile and environment,
then enable the replacement. Never run both tunnel units concurrently.

The tunnel unit uses the existing profile:

```text
digitalafarin-vps
```

and must target:

```text
http://127.0.0.1:3060/mcp
```

## Acceptance checks

### Local / CI

```bash
cd apps/api
python manage.py test control.tests -v 2
python manage.py check
python manage.py makemigrations --check --dry-run

cd ../../agent
PYTHONPATH=. pytest -q

cd ../mcp
PYTHONPATH=. pytest -q

cd ../apps/web
npm test
npm run lint
npm run build

cd ../..
PYTHONPATH=.:agent apps/api/.venv/bin/python apps/api/manage.py test acceptance.test_migration_readiness -v 2
git diff --check
grep -R "shell=True\|os.system\|subprocess.*shell" -n apps agent mcp || true
git grep -nE 'da_(agent|service|enroll)_[A-Za-z0-9]{8,}\.[A-Za-z0-9_-]{40,}' -- ':!*.md' || true
```

### Production VPS

```bash
sudo systemctl is-active \
  digitalafarin-platform-api \
  digitalafarin-platform-web \
  digitalafarin-platform-agent \
  digitalafarin-platform-mcp

sudo systemctl is-active digitalafarin-vps-tunnel || \
  sudo systemctl is-active digitalafarin-platform-mcp-tunnel

curl -fsS http://127.0.0.1:9750/health/
ss -ltnp | grep ':3060'
sudo -u digitalafarin-mcp -H sh -c 'set -a; . /home/digitalafarin-mcp/.config/tunnel-client/digitalafarin-vps.env; exec tunnel-client doctor --profile digitalafarin-vps --explain'
```

`ss` must show MCP listening on loopback only, never `0.0.0.0:3060` or `[::]:3060`.

Then invoke from the ChatGPT connector, in order:

```text
vps_list_servers()
vps_get_server()
vps_get_metrics()
vps_list_services()
```

Acceptance requires actual primary-VPS values, a recent snapshot with `stale=false`, and no credential/token in any tool output.

## Security boundary

1. No arbitrary shell/command tool exists in the MCP or Agent.
2. Agent service inventory is prefix allow-listed.
3. Every VPS receives a different agent credential; Django stores only credential digests.
4. MCP uses an independent operator principal with explicit inventory and typed-operation scopes.
5. MCP listens on `127.0.0.1` and is exposed to ChatGPT only through the Secure MCP Tunnel.
6. Write operations use typed payloads, scoped identities, full lifecycle audit,
   bounded output, and protected-unit enforcement. There is no arbitrary shell.
7. Legacy `agent_url`, shared agent token and manual-sync paths remain only for migration compatibility and will be removed in an explicit cleanup change after production acceptance.

## Next milestones

1. Complete project-by-project production migration using the runbook
2. Remove legacy shared-agent and manual-sync compatibility only after production acceptance
3. Add approval policy and scheduled deployment windows
4. Add backup automation and restore drills
5. Add alerts and scheduled jobs
