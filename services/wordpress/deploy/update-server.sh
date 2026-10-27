#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="digitalafarin-wordpress-mcp"
APP_DIR="/var/www/${APP_NAME}"
DASHBOARD_DIR="${APP_DIR}/dashboard"
DASHBOARD_ENV="/etc/digitalafarin-wp-agent.env"
MCP_ENV="/etc/${APP_NAME}.env"
EXPECTED_VERSION="0.8.0"

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
if ! grep -q '^GSC_BROKER_URL=' "${MCP_ENV}"; then
  printf '\nGSC_BROKER_URL=http://127.0.0.1:3040/api/internal/gsc\n' >>"${MCP_ENV}"
fi

chown -R deploy:deploy "${APP_DIR}"

# Theme Automation can modify production PHP only when its own Bridge safety
# harness and syntax checks pass. Skip these gates only on hosts without PHP;
# those hosts will report ZIP fallback for direct template writes.
if command -v php >/dev/null 2>&1; then
  sudo -u deploy bash -c "
    set -Eeuo pipefail
    cd '${APP_DIR}'
    php wordpress-plugin/digitalafarin-agent-bridge/tests/run.php
    find wordpress-plugin/digitalafarin-agent-bridge -name '*.php' -print0 | xargs -0 -n1 php -l
  "
fi

# Build and restart the dashboard first because MCP resolves WordPress and GSC
# credentials through localhost-only broker endpoints. Product integration
# credentials are stored encrypted in PostgreSQL and do not need build-time env.
sudo -u deploy npm --prefix "${DASHBOARD_DIR}" ci
set -a
source "${DASHBOARD_ENV}"
set +a
sudo --preserve-env=DATABASE_URL,ADMIN_PASSWORD_SHA256,SESSION_SECRET,CREDENTIALS_ENCRYPTION_KEY \
  -u deploy env NEXT_TELEMETRY_DISABLED=1 npm --prefix "${DASHBOARD_DIR}" run build
systemctl restart digitalafarin-wp-agent.service

for attempt in {1..15}; do
  if curl --fail --silent --show-error -H 'x-digitalafarin-internal-mcp: 1' \
    "http://127.0.0.1:3040/api/internal/sites" >/dev/null && \
     curl --fail --silent --show-error -H 'x-digitalafarin-internal-mcp: 1' \
    "http://127.0.0.1:3040/api/internal/gsc" >/dev/null; then
    break
  fi
  if [[ "$attempt" -eq 15 ]]; then
    journalctl -u digitalafarin-wp-agent.service -n 80 --no-pager >&2
    exit 1
  fi
  sleep 2
done

sudo -u deploy npm --prefix "${APP_DIR}" ci
sudo -u deploy npm --prefix "${APP_DIR}" test
systemctl restart "${APP_NAME}.service"

health="$(curl --fail --silent --show-error "http://127.0.0.1:3030/health")"
printf '%s\n' "${health}"
if ! grep -q "\"version\":\"${EXPECTED_VERSION}\"" <<<"${health}"; then
  echo "Unexpected MCP health version; expected ${EXPECTED_VERSION}." >&2
  exit 1
fi
