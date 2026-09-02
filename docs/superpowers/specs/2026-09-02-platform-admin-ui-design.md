# DigitalAfarin Platform Admin UI Design

## Goal
Build the production read-only administration UI for DigitalAfarin Platform on top of the existing `/api/control/v1/*` Django Control Plane APIs. The UI is RTL-first, Persian-first, multi-server aware, and must use real server/metrics/services/audit data with no mocks.

## Scope
Phase 1 includes:
- Overview dashboard
- Server list and server detail views
- Service inventory with status filtering
- Audit/activity view
- Responsive navigation shell
- Freshness/offline/stale states
- API error and empty states

Out of scope for this phase:
- start/stop/restart
- live journal logs
- deploy/rollback
- domains/SSL
- databases/backups
- environment-variable editing

These are represented as disabled/coming-later navigation items only when useful; no fake actions are presented as functional.

## Architecture
The Next.js app is a server-rendered client of the Django Control Plane. Browser code never receives the service-principal credential. All reads happen in server components through `apps/web/lib/control-plane.ts`, using `PLATFORM_API_URL` and `PLATFORM_API_TOKEN` from the server runtime environment.

The web UI must not call Host Agent or PostgreSQL directly. It consumes only these Control Plane endpoints:
- `GET /api/control/v1/servers/`
- `GET /api/control/v1/servers/{id|default}/`
- `GET /api/control/v1/servers/{id|default}/metrics/`
- `GET /api/control/v1/servers/{id|default}/services/`
- `GET /api/control/v1/audit/`

## Information Architecture
Primary navigation:
- نمای کلی (`/`)
- سرورها (`/servers`)
- سرویس‌ها (`/services`)
- فعالیت‌ها (`/activity`)
- استقرارها (disabled in phase 1)
- دامنه‌ها (disabled in phase 1)
- پشتیبان‌گیری (disabled in phase 1)
- تنظیمات (disabled in phase 1)

Overview shows fleet health, default server status, CPU/RAM/disk/uptime, service-health summary, unhealthy services, recent activity, and capability badges.

Server list shows every active server with status, hostname, freshness, and agent version. Server detail reuses metrics/service summaries scoped to one UUID.

Services page defaults to the default server and supports query-string `server` and `status` filters without client-side secrets.

Activity page shows audit records and may be scoped by `server`.

## Visual Direction
- Persian RTL application shell; technical identifiers remain LTR.
- Dark neutral interface optimized for long operations sessions.
- Dense but calm admin-console hierarchy, not a marketing dashboard.
- Status semantics: green=online/active, amber=stale/inactive, red=offline/failed, neutral=unknown.
- Desktop persistent sidebar; mobile top header + horizontally scrollable compact nav.
- No gradients, decorative illustrations, or fake charts.

## Data Contracts
TypeScript contracts mirror the existing serializers:

`ServerSummary`: UUID id, name, hostname, is_default, status, last_seen_at, age_seconds, agent_version, capabilities.

`MetricsSnapshot`: UUID id, name, status, cpu_percent, memory_percent, disk_percent, uptime_seconds, collected_at, age_seconds, stale.

`ServiceSnapshot`: unit_name, description, load_state, active_state, sub_state, last_seen_at.

`AuditEvent`: event_type, target_type, target_id, actor, metadata, created_at.

## Error Handling
The API client throws `ControlPlaneError` with status/code/message. Page-level components catch errors and render a visible operation state. `404`, `409 server_offline`, and `409 metrics_unavailable` are rendered as meaningful states, never swallowed into fake zero values.

## Security
- `PLATFORM_API_TOKEN` is server-only and never prefixed with `NEXT_PUBLIC_`.
- No browser fetch route proxies the raw token.
- No write endpoint is called in Phase 1.
- No arbitrary system command or systemd action is exposed.
- Technical IDs and API error details are escaped by React and not rendered via raw HTML.

## Testing
- Node built-in tests cover pure formatting/status/summary helpers.
- TypeScript/Next lint and build verify app integration.
- Production acceptance verifies pages against the already-running Control Plane on the VPS.

## Definition of Done
- Overview renders real Control Plane data.
- Multi-server list/detail render real UUID-backed servers.
- Services render real allow-listed systemd snapshots and identify failed services.
- Activity renders real audit events.
- stale/offline/error states are visible and accurate.
- UI is RTL and responsive.
- credential remains server-only.
- lint/build/tests pass before deployment.
