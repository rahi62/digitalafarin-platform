# DigitalAfarin Agency Control Center — Operations Runbook

This runbook covers the first production rollout and recovery of Agency Core, PostgreSQL persistence, the RTL Next.js Control Center and the existing WordPress MCP executor. It intentionally keeps both MCP transports private on localhost and keeps the existing Secure MCP Tunnels independent.

## Production topology

- Agency Core / MCP: `127.0.0.1:3050`
- WordPress MCP: `127.0.0.1:3030`
- Agency Admin: `127.0.0.1:3060`
- Public Admin origin: `https://agency.digitalafarin.ir`
- Public `/mcp`: must return `404`
- PostgreSQL: local/private only
- Legacy JSON: retained as a rollback source after PostgreSQL cutover

Do not modify the existing WordPress MCP tunnel while deploying the Agency Control Center.

## Preflight

Before changing production, confirm the reviewed commit has green Backend and Admin CI. On the VPS, confirm the current Agency MCP and WordPress MCP health endpoints respond before touching storage or Nginx.

```bash
curl -fsS http://127.0.0.1:3050/health
curl -fsS http://127.0.0.1:3030/health
systemctl is-active digitalafarin-agency-mcp.service
```

Confirm `agency.digitalafarin.ir` resolves to the VPS before requesting TLS. Confirm ports `3030`, `3050` and `3060` are not exposed on wildcard interfaces.

## PostgreSQL provisioning

Create a dedicated database and login. Generate the password on the VPS and do not commit or paste it into GitHub.

```bash
sudo -u postgres psql
```

Inside `psql`, create a dedicated login and database using a strong generated password, then exit. Store the resulting `DATABASE_URL` only in `/etc/digitalafarin-agency-mcp.env`, mode `600`.

Before cutover, the environment must still contain:

```text
STORE_DRIVER=json
ADMIN_ORIGIN=https://agency.digitalafarin.ir
SESSION_COOKIE_NAME=digitalafarin_agency_session
```

`CSRF_SECRET` must be a long random production value. Never reuse the database password as the CSRF secret.

## PostgreSQL backup

Before every future schema or application rollout, create a PostgreSQL dump and preserve the retained JSON rollback source.

```bash
sudo install -d -m 700 /var/backups/digitalafarin-agency
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
set -a
source /etc/digitalafarin-agency-mcp.env
set +a
pg_dump --format=custom --file="/var/backups/digitalafarin-agency/agency-$STAMP.dump" "$DATABASE_URL"
cp /var/www/digitalafarin-agency-mcp/data/agency.json \
  "/var/backups/digitalafarin-agency/agency-json-$STAMP.json"
chmod 600 /var/backups/digitalafarin-agency/agency-*$STAMP.*
```

Do not delete the JSON source immediately after the first successful PostgreSQL cutover.

## First PostgreSQL cutover

The rollout script is deliberately ordered as backup → migration → seed → JSON import → UUID/timestamp verification → persistence switch → health check. If verification fails, `STORE_DRIVER` is not changed. If the service fails after the switch, the environment file is restored and Agency is restarted on JSON.

```bash
cd /var/www/digitalafarin-agency-mcp
sudo bash deploy/rollout-postgres.sh
```

After the command returns success, verify:

```bash
grep '^STORE_DRIVER=' /etc/digitalafarin-agency-mcp.env
curl -fsS http://127.0.0.1:3050/health
```

The expected driver is `postgres`.

## Super Admin bootstrap

Do not permanently store `BOOTSTRAP_ADMIN_PASSWORD` in `/etc/digitalafarin-agency-mcp.env`. Bootstrap the first account with transient shell variables and immediately unset them.

```bash
cd /var/www/digitalafarin-agency-mcp
set -a
source /etc/digitalafarin-agency-mcp.env
set +a

read -r -p 'Admin email: ' BOOTSTRAP_ADMIN_EMAIL
read -r -p 'Admin display name: ' BOOTSTRAP_ADMIN_NAME
read -r -s -p 'Admin password: ' BOOTSTRAP_ADMIN_PASSWORD
echo
export BOOTSTRAP_ADMIN_EMAIL BOOTSTRAP_ADMIN_NAME BOOTSTRAP_ADMIN_PASSWORD

sudo -u deploy --preserve-env=DATABASE_URL,BOOTSTRAP_ADMIN_EMAIL,BOOTSTRAP_ADMIN_NAME,BOOTSTRAP_ADMIN_PASSWORD \
  npm run db:seed

unset BOOTSTRAP_ADMIN_PASSWORD BOOTSTRAP_ADMIN_EMAIL BOOTSTRAP_ADMIN_NAME
```

Do not place the password in command-line arguments, Git commits, screenshots or shell scripts.

## Admin install

Build and install the localhost-only Next.js Admin service:

```bash
cd /var/www/digitalafarin-agency-mcp
sudo bash deploy/install-admin.sh
curl -fsS http://127.0.0.1:3060/login >/dev/null
systemctl is-active digitalafarin-agency-admin.service
```

## Nginx and TLS

Copy the supplied vhost as a starting point and inspect it before enabling it.

```bash
sudo cp deploy/nginx-agency-control-center.conf.example /etc/nginx/sites-available/agency.digitalafarin.ir
sudo ln -sfn /etc/nginx/sites-available/agency.digitalafarin.ir /etc/nginx/sites-enabled/agency.digitalafarin.ir
sudo nginx -t
sudo systemctl reload nginx
```

Obtain/deploy TLS using the VPS's existing Certbot procedure, then test Nginx again. The public vhost must proxy `/api/` to `127.0.0.1:3050`, the UI to `127.0.0.1:3060`, and explicitly return `404` for `/mcp`.

## Production acceptance

Run the automated read-only verification after PostgreSQL cutover, Admin install and TLS deployment:

```bash
cd /var/www/digitalafarin-agency-mcp
sudo bash deploy/verify-production.sh
```

It verifies local health, localhost-only listeners, public `/mcp = 404`, unauthenticated API rejection, retained JSON/PostgreSQL consistency, Agency MCP tool discovery/invocation, WordPress MCP tool discovery and Nginx syntax.

Then manually log in to `https://agency.digitalafarin.ir` and verify Dashboard, Projects, Tasks, Departments, Approvals, Activity and Integrations render. On Integrations, run WordPress health and tool discovery. Tool discovery is read-only and must not execute WordPress mutations.

## Approval safety check

Create or inspect a `high`/`critical` task in a non-production test context and confirm the backend forces approval. Confirm the UI cannot directly execute a high-risk action without an approved Approval record. Do not test destructive WordPress actions on a live customer page.

## WordPress MCP regression

The existing WordPress MCP is a separate executor and must remain independently healthy.

```bash
curl -fsS http://127.0.0.1:3030/health
cd /var/www/digitalafarin-agency-mcp
sudo -u deploy npm run acceptance:mcp
```

The smoke command performs only MCP discovery/read calls. After deployment, also verify from ChatGPT that the existing DigitalAfarin WordPress connector still discovers its tools and can perform an explicitly chosen safe read operation. Do not alter the existing WordPress tunnel configuration as part of this deployment.

## Restore drill

At least once before calling the rollout operationally complete, restore a fresh PostgreSQL dump into a temporary database on the VPS. Do not overwrite production.

```bash
sudo -u postgres createdb digitalafarin_agency_restore_test
sudo -u postgres pg_restore --dbname=digitalafarin_agency_restore_test \
  /var/backups/digitalafarin-agency/agency-<STAMP>.dump
sudo -u postgres psql -d digitalafarin_agency_restore_test -c 'select count(*) from projects;'
sudo -u postgres psql -d digitalafarin_agency_restore_test -c 'select count(*) from tasks;'
sudo -u postgres psql -d digitalafarin_agency_restore_test -c 'select count(*) from decisions;'
sudo -u postgres psql -d digitalafarin_agency_restore_test -c 'select count(*) from notes;'
sudo -u postgres dropdb digitalafarin_agency_restore_test
```

Compare representative counts with production. For the first migration, also verify the known DigitalAfarin project UUID and representative task/decision IDs are present.

## Rollback to JSON

Use this only if PostgreSQL-backed Agency becomes unhealthy and normal repair is not immediately safe. The retained JSON source must still exist.

```bash
sudo cp /etc/digitalafarin-agency-mcp.env /etc/digitalafarin-agency-mcp.env.failed-postgres
sudo sed -i 's/^STORE_DRIVER=.*/STORE_DRIVER=json/' /etc/digitalafarin-agency-mcp.env
sudo systemctl restart digitalafarin-agency-mcp.service
curl -fsS http://127.0.0.1:3050/health
```

If a timestamped pre-cutover environment backup created by `deploy/rollout-postgres.sh` is available, restoring that complete file is preferred to editing individual settings. Keep PostgreSQL intact for investigation; do not drop the database during rollback.

## Admin-only rollback

If the Admin UI has a problem while Agency MCP is healthy, isolate the UI without touching MCP persistence or either tunnel:

```bash
sudo systemctl stop digitalafarin-agency-admin.service
sudo rm -f /etc/nginx/sites-enabled/agency.digitalafarin.ir
sudo nginx -t && sudo systemctl reload nginx
```

Agency MCP can continue serving ChatGPT through its independent Secure MCP Tunnel.

## Post-deploy evidence to record

Record the deployed Git SHA, CI run, JSON backup path, PostgreSQL dump path, migration verifier result, Agency health result, Admin health result, Nginx test, public `/mcp` status, MCP smoke result and WordPress regression result. Never record passwords, database URLs, session tokens or CSRF secrets in the deployment report.
