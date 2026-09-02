# DigitalAfarin Platform Admin UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Phase 1 RTL administration UI for DigitalAfarin Platform using the live read-only Control Plane APIs.

**Architecture:** Next.js server components call Django Control Plane through one server-only typed API client. Shared layout/components render fleet, metrics, services, and audit data without exposing credentials to the browser. Query-string filters stay server-rendered.

**Tech Stack:** Next.js 16.3.3, React 19, TypeScript 5.8, CSS, Node built-in test runner.

**Spec:** `docs/superpowers/specs/2026-09-02-platform-admin-ui-design.md`

## Global Constraints
- Persian-first RTL UI; technical identifiers stay LTR.
- Use only `/api/control/v1/*`; do not use legacy `/api/servers/*` sync routes.
- `PLATFORM_API_TOKEN` remains server-only.
- Phase 1 is read-only.
- No new UI dependency is required.
- No fake/mock production data.

---

### Task 1: Typed Control Plane client and dashboard helpers

**Files:**
- Create: `apps/web/lib/control-plane.ts`
- Create: `apps/web/lib/dashboard.ts`
- Create: `apps/web/lib/dashboard.test.ts`
- Modify: `apps/web/package.json`
- Delete: `apps/web/lib/api.ts`
- Delete: `apps/web/app/api/sync/route.ts`
- Delete: `apps/web/components/SyncButton.tsx`

**Interfaces:**
- Produces `listServers`, `getServer`, `getMetrics`, `listServices`, `listAuditEvents`.
- Produces `formatUptime`, `formatAge`, `summarizeServices`, `statusTone`.

- [ ] Write failing Node tests for formatting and service summary.
- [ ] Run `node --test apps/web/lib/dashboard.test.ts` and confirm RED because helpers do not exist.
- [ ] Implement helpers and typed API client.
- [ ] Run Node tests and confirm PASS.
- [ ] Remove legacy sync client/route/button.
- [ ] Commit `feat: add typed control plane web client`.

### Task 2: Application shell and reusable operational components

**Files:**
- Create: `apps/web/components/AppShell.tsx`
- Create: `apps/web/components/StatusBadge.tsx`
- Create: `apps/web/components/MetricCard.tsx`
- Create: `apps/web/components/ServiceTable.tsx`
- Create: `apps/web/components/EmptyState.tsx`
- Modify: `apps/web/app/layout.tsx`
- Modify: `apps/web/app/globals.css`

**Interfaces:**
- Consumes dashboard helper status tones and serializer-shaped props.
- Produces a responsive RTL shell reused by all pages.

- [ ] Implement the shared component contracts without client-side data fetching.
- [ ] Replace legacy global CSS with the operational design system.
- [ ] Run `npx tsc --noEmit` and `npm run lint`.
- [ ] Commit `feat: add rtl platform application shell`.

### Task 3: Real-data overview dashboard

**Files:**
- Modify: `apps/web/app/page.tsx`

**Interfaces:**
- Consumes `listServers`, `getServer("default")`, `getMetrics("default")`, `listServices("default")`, and `listAuditEvents`.

- [ ] Render fleet/default-server summary and freshness.
- [ ] Render CPU/RAM/disk/uptime cards using real values.
- [ ] Render service-health summary and unhealthy services.
- [ ] Render recent audit activity.
- [ ] Verify TypeScript/lint.
- [ ] Commit `feat: build live platform overview`.

### Task 4: Multi-server pages

**Files:**
- Create: `apps/web/app/servers/page.tsx`
- Create: `apps/web/app/servers/[serverId]/page.tsx`

**Interfaces:**
- Server IDs are public UUIDs or `default`; no integer legacy IDs.

- [ ] Implement server fleet cards/table.
- [ ] Implement scoped server detail with metrics and services.
- [ ] Render stale/offline and metrics-unavailable states.
- [ ] Verify TypeScript/lint.
- [ ] Commit `feat: add multi-server admin views`.

### Task 5: Services and audit pages

**Files:**
- Create: `apps/web/app/services/page.tsx`
- Create: `apps/web/app/activity/page.tsx`

**Interfaces:**
- Query params: `server=<uuid|default>`, `status=<active|failed|inactive>`.
- Audit query params: `server=<uuid>`, optional `limit` fixed by UI to safe values.

- [ ] Implement server/status filters as standard links/forms without secrets.
- [ ] Render all allow-listed service snapshots and highlight failed services.
- [ ] Render audit event actor/type/target/metadata/time.
- [ ] Verify TypeScript/lint.
- [ ] Commit `feat: add services and audit consoles`.

### Task 6: Production build and deployment handoff

**Files:**
- Modify: `README.md`
- Create: `infra/systemd/digitalafarin-platform-web.service`

**Interfaces:**
- Web runtime uses `PLATFORM_API_URL=http://127.0.0.1:9750` and existing read-only service-principal token.
- Next.js listens only on `127.0.0.1:9760` pending Nginx publication.

- [ ] Document environment and startup commands.
- [ ] Add the systemd unit with loopback binding.
- [ ] Run Node tests, `npm run lint`, and `npm run build`.
- [ ] Run secret-pattern and legacy-route scans.
- [ ] Commit `chore: prepare platform admin web deployment`.
