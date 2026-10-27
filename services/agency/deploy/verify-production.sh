#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/digitalafarin-agency-mcp}"
ENV_FILE="${ENV_FILE:-/etc/digitalafarin-agency-mcp.env}"
PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-https://agency.digitalafarin.ir}"

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

pass() {
  echo "[PASS] $*"
}

if [[ "${EUID}" -ne 0 ]]; then
  fail "Run as root: sudo bash deploy/verify-production.sh"
fi
if [[ ! -f "$ENV_FILE" ]]; then
  fail "Missing environment file: $ENV_FILE"
fi
if [[ ! -d "$APP_DIR" ]]; then
  fail "Missing Agency application directory: $APP_DIR"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

DATA_FILE="${DATA_FILE:-$APP_DIR/data/agency.json}"
STORE_DRIVER="${STORE_DRIVER:-json}"
DATABASE_URL="${DATABASE_URL:-}"

systemctl is-active --quiet digitalafarin-agency-mcp.service || fail "Agency MCP service is not active"
pass "Agency MCP systemd service is active"

systemctl is-active --quiet digitalafarin-agency-admin.service || fail "Agency Admin service is not active"
pass "Agency Admin systemd service is active"

curl --fail --silent --show-error http://127.0.0.1:3050/health >/dev/null || fail "Agency MCP local health failed"
pass "Agency MCP local health"

curl --fail --silent --show-error http://127.0.0.1:3030/health >/dev/null || fail "WordPress MCP local health failed"
pass "WordPress MCP local health"

curl --fail --silent --show-error http://127.0.0.1:3061/login >/dev/null || fail "Agency Admin local login route failed"
pass "Agency Admin local route"

for port in 3030 3050 3061; do
  LISTENERS="$(ss -ltnH | awk '{print $4}')"
  if ! grep -Eq "(^|:)127\.0\.0\.1:${port}$|^\[::1\]:${port}$" <<<"$LISTENERS"; then
    fail "Expected localhost listener missing on port $port"
  fi
  if grep -Eq "(^|:)0\.0\.0\.0:${port}$|^\[::\]:${port}$" <<<"$LISTENERS"; then
    fail "Port $port is exposed on a wildcard interface"
  fi
  pass "Port $port is localhost-only"
done

curl --fail --silent --show-error "$PUBLIC_ORIGIN/login" >/dev/null || fail "Public Admin login route failed"
pass "Public HTTPS Admin route"

MCP_PUBLIC_STATUS="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$PUBLIC_ORIGIN/mcp")"
[[ "$MCP_PUBLIC_STATUS" == "404" ]] || fail "Public /mcp must return 404, got $MCP_PUBLIC_STATUS"
pass "Public /mcp is not exposed"

AUTH_PUBLIC_STATUS="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$PUBLIC_ORIGIN/api/v1/auth/me")"
[[ "$AUTH_PUBLIC_STATUS" == "401" ]] || fail "Unauthenticated API must return 401, got $AUTH_PUBLIC_STATUS"
pass "Admin API requires authentication"

if [[ "$STORE_DRIVER" == "postgres" ]]; then
  if [[ -z "$DATABASE_URL" ]]; then
    fail "STORE_DRIVER=postgres but DATABASE_URL is empty"
  fi
  sudo -u deploy env DATABASE_URL="$DATABASE_URL" DATA_FILE="$DATA_FILE" bash -lc \
    "cd '$APP_DIR' && npm run store:verify -- '$DATA_FILE'" >/dev/null || fail "PostgreSQL import verification failed"
  pass "PostgreSQL data matches retained JSON migration source"
else
  echo "[WARN] STORE_DRIVER=$STORE_DRIVER; PostgreSQL verification skipped"
fi

sudo -u deploy bash -lc "cd '$APP_DIR' && npm run acceptance:mcp" || fail "MCP acceptance smoke failed"
pass "Agency and WordPress MCP discovery/read acceptance"

nginx -t >/dev/null 2>&1 || fail "Nginx configuration test failed"
pass "Nginx configuration"

echo "Production acceptance checks completed successfully."
