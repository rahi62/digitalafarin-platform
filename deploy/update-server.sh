#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="digitalafarin-wordpress-mcp"
APP_DIR="/var/www/${APP_NAME}"
DASHBOARD_DIR="${APP_DIR}/dashboard"
DASHBOARD_ENV="/etc/digitalafarin-wp-agent.env"
MCP_ENV="/etc/${APP_NAME}.env"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root or via the restricted sudo rule." >&2
  exit 1
fi

test -f "${MCP_ENV}"
test -f "${DASHBOARD_ENV}"
test -f "${APP_DIR}/package-lock.json"
test -f "${DASHBOARD_DIR}/package-lock.json"

if ! grep -q '^MAX_MEDIA_BYTES=' "${MCP_ENV}"; then
  printf '\nMAX_MEDIA_BYTES=10000000\n' >>"${MCP_ENV}"
fi

chown -R deploy:deploy "${APP_DIR}"

# Build and restart the dashboard first because MCP resolves enabled sites and
# encrypted credentials through its localhost-only broker endpoint.
sudo -u deploy npm --prefix "${DASHBOARD_DIR}" ci
set -a
source "${DASHBOARD_ENV}"
set +a
sudo --preserve-env=DATABASE_URL,ADMIN_PASSWORD_SHA256,SESSION_SECRET,CREDENTIALS_ENCRYPTION_KEY \
  -u deploy env NEXT_TELEMETRY_DISABLED=1 npm --prefix "${DASHBOARD_DIR}" run build
systemctl restart digitalafarin-wp-agent.service

for attempt in {1..15}; do
  if curl --fail --silent --show-error -H 'x-digitalafarin-internal-mcp: 1' \
    "http://127.0.0.1:3040/api/internal/sites" >/dev/null; then
    break
  fi
  if [[ "$attempt" -eq 15 ]]; then
    journalctl -u digitalafarin-wp-agent.service -n 80 --no-pager >&2
    exit 1
  fi
  sleep 2
done

sudo -u deploy npm --prefix "${APP_DIR}" ci
sudo -u deploy npm --prefix "${APP_DIR}" run build
systemctl restart "${APP_NAME}.service"
curl --fail --silent --show-error "http://127.0.0.1:3030/health"
