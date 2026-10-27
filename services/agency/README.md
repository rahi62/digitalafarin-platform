# DigitalAfarin Agency Core

DigitalAfarin's central operating backend and ChatGPT MCP connector. ChatGPT remains the reasoning engine; Agency Core owns durable project memory, decisions, tasks, departments, approvals, audit activity, RBAC and integration registry state.

The repository also contains the internal Persian/RTL **Agency Control Center** under `admin/`.

## Architecture

```text
ChatGPT
  │ MCP via Secure MCP Tunnel
  ▼
Agency Core 127.0.0.1:3050
  ├─ MCP /mcp
  ├─ REST /api/v1
  ├─ Auth / RBAC / Approvals / Activity
  └─ PostgreSQL
         ▲
         │ same-origin REST
Next.js Control Center 127.0.0.1:3060

Independent executors
  └─ DigitalAfarin WordPress MCP 127.0.0.1:3030
```

The public Admin vhost is `https://agency.digitalafarin.ir`. Public `/mcp` on that vhost must return `404`; ChatGPT reaches Agency MCP only through the independent Secure MCP Tunnel.

## MCP tools

- `agency_get_team`
- `agency_prepare_council`
- `agency_list_projects`
- `agency_get_project`
- `agency_upsert_project`
- `agency_add_note`
- `agency_record_decision`
- `agency_create_task`
- `agency_update_task`

Existing tool contracts remain backward compatible while PostgreSQL becomes the authoritative store.

## Core development

```bash
cp .env.example .env
npm install
npm run check
npm test
npm run build
```

Useful commands:

```bash
npm run db:migrate
npm run db:seed
npm run store:import -- ./data/agency.json
npm run store:verify -- ./data/agency.json
npm run acceptance:mcp
```

Core health: `http://127.0.0.1:3050/health`

Core MCP: `http://127.0.0.1:3050/mcp`

## Admin development

```bash
cd admin
npm install
npm run check
npm run check:rtl
npm run test:rtl
npm run build
npm run dev
```

The Admin is Persian-first and RTL-first. Layout code uses logical CSS properties so a future LTR mode does not require a structural rewrite.

## ChatGPT connection

Use the same Secure MCP Tunnel pattern as the existing DigitalAfarin WordPress connector, but point the Agency tunnel at:

```text
http://127.0.0.1:3050/mcp
```

Suggested app name: `DigitalAfarin Agency`.

Example prompts:

- `@DigitalAfarin Agency تیم را نمایش بده و هیچ تغییری ایجاد نکن.`
- `@DigitalAfarin Agency پروژه‌های من را نمایش بده.`
- `@DigitalAfarin Agency برای پروژه X اتاق فکر SEO + UX + Product تشکیل بده و نتیجه را Chief of Staff جمع‌بندی کند.`
- `@DigitalAfarin Agency تصمیم نهایی این جلسه را در پروژه ثبت کن.`

## WordPress integration boundary

The existing DigitalAfarin WordPress MCP remains a separate service and connector. Agency registers it as an executor but does not merge its code or tunnel into Agency Core.

The first integration milestone is intentionally read-only: health plus MCP `tools/list` discovery. No WordPress mutation is exposed by the integration discovery endpoint.

## VPS deployment

Initial/server update:

```bash
cd /var/www/digitalafarin-agency-mcp
sudo bash deploy/install-server.sh
```

PostgreSQL cutover:

```bash
sudo bash deploy/rollout-postgres.sh
```

Admin install:

```bash
sudo bash deploy/install-admin.sh
```

Production acceptance after Nginx/TLS:

```bash
sudo bash deploy/verify-production.sh
```

The detailed first-rollout, backup, restore and rollback procedure is in `docs/operations/agency-control-center-runbook.md`.

### Preferred Git deployment

```bash
sudo mkdir -p /var/www/digitalafarin-agency-mcp
sudo chown deploy:deploy /var/www/digitalafarin-agency-mcp
sudo -u deploy git clone git@github.com:rahi62/digitalafarin-agency-mcp.git /var/www/digitalafarin-agency-mcp
cd /var/www/digitalafarin-agency-mcp
sudo bash deploy/install-server.sh
```

For later updates:

```bash
cd /var/www/digitalafarin-agency-mcp
sudo -u deploy git pull --ff-only origin main
sudo bash deploy/install-server.sh
```
