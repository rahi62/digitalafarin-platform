#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="digitalafarin-wordpress-mcp"
APP_DIR="/var/www/${APP_NAME}"
ENV_FILE="/etc/${APP_NAME}.env"
SERVICE_SOURCE="${APP_DIR}/deploy/${APP_NAME}.service"
SERVICE_TARGET="/etc/systemd/system/${APP_NAME}.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root: sudo bash deploy/install-server.sh" >&2
  exit 1
fi

if ! id deploy >/dev/null 2>&1; then
  echo "Required user 'deploy' does not exist." >&2
  exit 1
fi

if [[ ! -f "${APP_DIR}/package-lock.json" ]]; then
  echo "Project files are missing from ${APP_DIR}." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  install -o root -g root -m 600 /dev/null "${ENV_FILE}"
  cat >"${ENV_FILE}" <<'ENV'
SITE_BROKER_URL=http://127.0.0.1:3040/api/internal/sites
PORT=3030
HOST=127.0.0.1
ALLOWED_ORIGINS=https://chatgpt.com
MAX_POST_CONTENT_BYTES=500000
ENV
fi

# Remove obsolete single-site credentials from older installations. Credentials
# are now resolved from the dashboard's encrypted PostgreSQL registry.
sed -i '/^WP_BASE_URL=/d;/^WP_USERNAME=/d;/^WP_APP_PASSWORD=/d' "${ENV_FILE}"
if ! grep -q '^SITE_BROKER_URL=' "${ENV_FILE}"; then
  printf '\nSITE_BROKER_URL=http://127.0.0.1:3040/api/internal/sites\n' >>"${ENV_FILE}"
fi

if ! curl --fail --silent --show-error -H 'x-digitalafarin-internal-mcp: 1' \
  "http://127.0.0.1:3040/api/internal/sites" >/dev/null; then
  echo "Dashboard site broker is not reachable. Deploy/start the dashboard first." >&2
  exit 3
fi

chown -R deploy:deploy "${APP_DIR}"
sudo -u deploy npm --prefix "${APP_DIR}" ci
sudo -u deploy npm --prefix "${APP_DIR}" run build

install -o root -g root -m 644 "${SERVICE_SOURCE}" "${SERVICE_TARGET}"
systemctl daemon-reload
systemctl enable --now "${APP_NAME}.service"
systemctl restart "${APP_NAME}.service"

if ! curl --fail --silent --show-error "http://127.0.0.1:3030/health" >/dev/null; then
  journalctl -u "${APP_NAME}.service" -n 50 --no-pager >&2
  exit 1
fi

echo "${APP_NAME} is healthy at http://127.0.0.1:3030"
