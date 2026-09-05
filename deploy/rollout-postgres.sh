#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/digitalafarin-agency-mcp}"
ENV_FILE="${ENV_FILE:-/etc/digitalafarin-agency-mcp.env}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/data/backups}"
SERVICE="digitalafarin-agency-mcp.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/rollout-postgres.sh" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing environment file: $ENV_FILE" >&2
  exit 1
fi
if [[ ! -f "$APP_DIR/package.json" ]]; then
  echo "Agency package not found at $APP_DIR" >&2
  exit 1
fi
if ! id deploy >/dev/null 2>&1; then
  echo "deploy user does not exist" >&2
  exit 1
fi

# Load production configuration as root, but run application/database commands unprivileged.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

DATA_FILE="${DATA_FILE:-$APP_DIR/data/agency.json}"
STORE_DRIVER="${STORE_DRIVER:-json}"
DATABASE_URL="${DATABASE_URL:-}"
ADMIN_ORIGIN="${ADMIN_ORIGIN:-}"
CSRF_SECRET="${CSRF_SECRET:-}"

if [[ "$STORE_DRIVER" == "postgres" ]]; then
  echo "STORE_DRIVER is already postgres; refusing to repeat the cutover automatically." >&2
  exit 2
fi
if [[ "$STORE_DRIVER" != "json" ]]; then
  echo "Expected STORE_DRIVER=json before cutover, got: $STORE_DRIVER" >&2
  exit 1
fi
if [[ -z "$DATABASE_URL" || "$DATABASE_URL" == *"change-me"* ]]; then
  echo "DATABASE_URL must contain the real production PostgreSQL credential." >&2
  exit 1
fi
if [[ "$ADMIN_ORIGIN" != "https://agency.digitalafarin.ir" ]]; then
  echo "ADMIN_ORIGIN must be https://agency.digitalafarin.ir" >&2
  exit 1
fi
if (( ${#CSRF_SECRET} < 32 )); then
  echo "CSRF_SECRET must contain at least 32 characters." >&2
  exit 1
fi
if [[ ! -s "$DATA_FILE" ]]; then
  echo "Legacy JSON store is missing or empty: $DATA_FILE" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$BACKUP_DIR/agency-before-postgres-$STAMP.json"
ENV_BACKUP="$BACKUP_DIR/digitalafarin-agency-mcp-$STAMP.env"

# Rollback points are created before any database or service mutation.
cp -- "$DATA_FILE" "$BACKUP_FILE"
cp -- "$ENV_FILE" "$ENV_BACKUP"
chmod 600 "$BACKUP_FILE" "$ENV_BACKUP"
echo "Backups created: $BACKUP_FILE and $ENV_BACKUP"

# Apply committed schema, seed idempotent reference data, then import legacy project memory.
# Only DATABASE_URL is passed to these commands; bootstrap credentials are never inherited here.
sudo -u deploy env DATABASE_URL="$DATABASE_URL" npm --prefix "$APP_DIR" run db:migrate
sudo -u deploy env DATABASE_URL="$DATABASE_URL" npm --prefix "$APP_DIR" run db:seed
sudo -u deploy env DATABASE_URL="$DATABASE_URL" npm --prefix "$APP_DIR" run store:import -- "$DATA_FILE"

# Hard gate: UUIDs and timestamps from JSON must exist unchanged in PostgreSQL.
sudo -u deploy env DATABASE_URL="$DATABASE_URL" npm --prefix "$APP_DIR" run store:verify -- "$DATA_FILE"

# Only after verification succeeds is persistence switched to PostgreSQL.
if grep -q '^STORE_DRIVER=' "$ENV_FILE"; then
  sed -i 's/^STORE_DRIVER=.*/STORE_DRIVER=postgres/' "$ENV_FILE"
else
  printf '\nSTORE_DRIVER=postgres\n' >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

rollback_env() {
  echo "PostgreSQL cutover health check failed; restoring JSON persistence." >&2
  cp -- "$ENV_BACKUP" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  systemctl restart "$SERVICE" || true
}

if ! systemctl restart "$SERVICE"; then
  rollback_env
  exit 1
fi

sleep 2
if ! curl --fail --silent --show-error http://127.0.0.1:3050/health; then
  echo >&2
  rollback_env
  exit 1
fi
echo

# Keep the immutable JSON backup after a successful cutover; do not delete it.
systemctl --no-pager --full status "$SERVICE" | sed -n '1,20p'
echo "Agency persistence cutover verified. STORE_DRIVER=postgres is active."
