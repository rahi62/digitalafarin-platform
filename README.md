# DigitalAfarin Platform

Internal VPS control plane for DigitalAfarin. The first milestone is intentionally read-only: collect host metrics and inventory allow-listed systemd services, sync them into Django, and render the state in a Next.js admin dashboard.

## Architecture

```text
Next.js admin (apps/web)
        |
        v
Django control plane (apps/api)
        |
        v
Python host agent (agent/) -- bound to 127.0.0.1 only
        |
        +-- psutil metrics
        +-- systemctl read-only inventory
```

The browser never talks directly to the host agent. Agent credentials stay server-side. The agent does not accept arbitrary shell commands.

## Milestone 1 capabilities

- Server CPU, memory, disk and uptime metrics
- Allow-listed systemd service discovery
- Django persistence for servers and service snapshots
- Manual sync endpoint
- Audit event for each sync
- Next.js overview dashboard
- Read-only host agent with bearer authentication

## Local development

### 1. Agent

```bash
cd agent
python -m venv .venv
source .venv/bin/activate
pip install -e .
export PLATFORM_AGENT_TOKEN=dev-agent-token
export AGENT_SERVICE_PREFIXES=ssh,nginx
uvicorn digitalafarin_agent.main:app --host 127.0.0.1 --port 9743 --reload
```

### 2. Django API

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DJANGO_SECRET_KEY=dev-secret
export PLATFORM_API_TOKEN=dev-api-token
export PLATFORM_AGENT_TOKEN=dev-agent-token
python manage.py migrate
python manage.py seed_local_server --agent-url http://127.0.0.1:9743
python manage.py runserver 127.0.0.1:8000
```

### 3. Next.js admin

```bash
cd apps/web
npm install
export PLATFORM_API_URL=http://127.0.0.1:8000
export PLATFORM_API_TOKEN=dev-api-token
export PLATFORM_SERVER_ID=1
npm run dev
```

Open `http://localhost:3000`. Click **Sync server** to pull fresh host state through the Django control plane.

## Security boundary

Milestone 1 is deliberately read-only. Future privileged operations (restart, deploy, Nginx changes, certificates, database restore) must be explicit typed operations and must never accept free-form shell input. Production deployment should keep the agent on loopback or a Unix socket, use a dedicated service account, and apply narrowly scoped privilege escalation only to approved helpers.

## Next milestones

1. Auth/RBAC + immutable audit trail
2. Typed service actions: start/stop/restart
3. GitHub webhook + release-based deployment engine
4. Health checks + atomic symlink switch + rollback
5. Domains/Nginx + SSL
6. Environment secret management
7. PostgreSQL backup/restore
8. Alerts and scheduled jobs
