#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/var/www/digitalafarin-wordpress-mcp/dashboard"
ENV_FILE="/etc/digitalafarin-wp-agent.env"
SERVICE_NAME="digitalafarin-wp-agent"
SERVICE_SOURCE="/var/www/digitalafarin-wordpress-mcp/deploy/${SERVICE_NAME}.service"
SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install-dashboard.sh" >&2
  exit 1
fi

if [[ ! -f "${APP_DIR}/package-lock.json" ]]; then
  echo "Dashboard files are missing from ${APP_DIR}." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  install -o root -g root -m 600 /dev/null "${ENV_FILE}"
  cat >"${ENV_FILE}" <<'ENV'
DATABASE_URL=postgresql://wp_agent:REPLACE_DB_PASSWORD@127.0.0.1:5432/wp_agent
ADMIN_PASSWORD_SHA256=REPLACE_ADMIN_PASSWORD_SHA256
SESSION_SECRET=REPLACE_SESSION_SECRET
CREDENTIALS_ENCRYPTION_KEY=REPLACE_CREDENTIALS_ENCRYPTION_KEY
GSC_GOOGLE_CLIENT_ID=
GSC_GOOGLE_CLIENT_SECRET=
GSC_GOOGLE_REDIRECT_URI=https://wp-agent.digitalafarin.ir/api/gsc/oauth/callback
ENV
  echo "Created ${ENV_FILE}. Replace every REPLACE_* value, then rerun." >&2
  exit 2
fi

if grep -q "REPLACE_" "${ENV_FILE}"; then
  echo "Replace every placeholder in ${ENV_FILE}, then rerun." >&2
  exit 2
fi

chown -R deploy:deploy "/var/www/digitalafarin-wordpress-mcp"
sudo -u deploy npm --prefix "${APP_DIR}" ci
set -a
# The dashboard validates its server-only configuration while Next.js collects
# page data, so the protected environment must also be present during build.
source "${ENV_FILE}"
set +a
sudo --preserve-env=DATABASE_URL,ADMIN_PASSWORD_SHA256,SESSION_SECRET,CREDENTIALS_ENCRYPTION_KEY,GSC_GOOGLE_CLIENT_ID,GSC_GOOGLE_CLIENT_SECRET,GSC_GOOGLE_REDIRECT_URI \
  -u deploy env NEXT_TELEMETRY_DISABLED=1 npm --prefix "${APP_DIR}" run build

install -o root -g root -m 644 "${SERVICE_SOURCE}" "${SERVICE_TARGET}"
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"
systemctl restart "${SERVICE_NAME}.service"

for attempt in {1..15}; do
  if curl --fail --silent --show-error "http://127.0.0.1:3040/login" >/dev/null; then
    echo "${SERVICE_NAME} is healthy at http://127.0.0.1:3040"
    exit 0
  fi
  sleep 2
done

journalctl -u "${SERVICE_NAME}.service" -n 80 --no-pager >&2
exit 1
