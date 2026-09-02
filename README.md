# DigitalAfarin Platform

Internal VPS control plane for DigitalAfarin. The current milestone adds a multi-server, read-only operations path that lets authenticated agents report host state outbound to Django and exposes that state to ChatGPT through a localhost-only MCP server and the OpenAI Secure MCP Tunnel.

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

The browser and ChatGPT never receive agent credentials. The MCP does not contact host agents or PostgreSQL directly. Each VPS has an independent, revocable agent credential, and the MCP has its own read-only service-principal credential.

## Current capabilities

- Multi-server UUID identity with one optional active default server
- CPU, memory, disk and uptime snapshots
- Allow-listed systemd service discovery
- One-time agent enrollment with per-server credentials
- Outbound agent heartbeat ingestion
- Stale/offline detection from heartbeat freshness
- Scoped read-only Control Plane API
- Read-only MCP tools for servers, metrics, services and audit events
- Legacy single-server pull/manual sync kept temporarily for migration compatibility

The MCP v1 intentionally has no restart, deploy, shell, backup, Nginx-write or other state-changing tool.

## Local development

### 1. Django API

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DJANGO_SECRET_KEY=dev-secret
export PLATFORM_API_TOKEN=dev-api-token
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

Create the MCP service principal once in Django:

```bash
cd apps/api
source .venv/bin/activate
python manage.py create_service_principal chatgpt-vps-mcp
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

The existing web dashboard can continue using the legacy read API while the frontend is migrated to UUID-based endpoints:

```bash
cd apps/web
npm install
export PLATFORM_API_URL=http://127.0.0.1:8000
export PLATFORM_API_TOKEN=dev-api-token
export PLATFORM_SERVER_ID=1
npm run dev
```

## Production bootstrap: first VPS + MCP

Install the repository under `/opt/digitalafarin-platform`, create the service accounts used by the committed systemd units, create `/etc/digitalafarin-platform`, and install the API, Agent and MCP dependencies into their local `.venv` directories. Keep real credentials only in root/service-readable environment files, never in Git.

### 1. Migrate Django and create the one-time enrollment credential

```bash
cd /opt/digitalafarin-platform/apps/api
source .venv/bin/activate
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

### 3. Create the read-only MCP identity

```bash
python manage.py create_service_principal chatgpt-vps-mcp
```

Copy the one-time printed service credential into `/etc/digitalafarin-platform/mcp.env`:

```dotenv
CONTROL_PLANE_URL=http://127.0.0.1:9750
CONTROL_PLANE_TOKEN=<read-only service-principal credential>
MCP_HOST=127.0.0.1
MCP_PORT=3060
MCP_PATH=/mcp
```

Do **not** paste enrollment credentials, agent credentials or MCP service credentials into ChatGPT, issue trackers, Git commits, screenshots or logs.

### 4. Start MCP and the already-created Secure MCP Tunnel

Before enabling the tunnel service, verify the actual binary location:

```bash
command -v tunnel-client
```

The committed unit assumes `/usr/local/bin/tunnel-client`. If the command above returns another path, edit only `ExecStart` in `digitalafarin-platform-mcp-tunnel.service` during deployment.

The tunnel unit runs as `digitalafarin-mcp`, so verify the profile is readable by that same service account before enabling it:

```bash
sudo -u digitalafarin-mcp tunnel-client doctor --profile digitalafarin-vps --explain
```

If the profile was initialized under another Unix account, configure the `digitalafarin-vps` profile for `digitalafarin-mcp` rather than copying a private credential into Git or the unit file.

Then install/enable the committed units and start them:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now digitalafarin-platform-api
sudo systemctl enable --now digitalafarin-platform-agent
sudo systemctl enable --now digitalafarin-platform-mcp
sudo systemctl enable --now digitalafarin-platform-mcp-tunnel
```

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

cd ../../agent
PYTHONPATH=. pytest -q

cd ../mcp
PYTHONPATH=. pytest -q

cd ..
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
  digitalafarin-platform-mcp \
  digitalafarin-platform-mcp-tunnel

curl -fsS http://127.0.0.1:9750/health/
ss -ltnp | grep ':3060'
tunnel-client doctor --profile digitalafarin-vps --explain
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
4. MCP uses an independent read-only principal with explicit scopes.
5. MCP listens on `127.0.0.1` and is exposed to ChatGPT only through the Secure MCP Tunnel.
6. Write operations remain deferred until typed operations, RBAC, audit and approval boundaries are implemented.
7. Legacy `agent_url`, shared agent token and manual-sync paths remain only for migration compatibility and will be removed in an explicit cleanup change after production acceptance.

## Next milestones

1. Complete primary VPS production acceptance and ChatGPT read path
2. Migrate dashboard reads to UUID-based Control API
3. Typed service operations with approval: start/stop/restart
4. GitHub webhook + release-based deployment engine
5. Health checks + atomic activation + rollback
6. Domains/Nginx + SSL
7. Environment secret management
8. PostgreSQL backup/restore
9. Alerts and scheduled jobs
