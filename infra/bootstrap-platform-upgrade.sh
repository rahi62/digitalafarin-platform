#!/usr/bin/env bash
set -euo pipefail

REPO=/opt/digitalafarin-platform
EXPECTED_REPOSITORY=git@github.com:rahi62/digitalafarin-platform.git
COMMIT="${1:-}"

fail(){ printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ ${EUID} -eq 0 ]] || fail "run as root"
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "exact lowercase 40-character commit required"
[[ -d "$REPO/.git" ]] || fail "production repository is missing"

cd "$REPO"
origin="$(git remote get-url origin)"
case "$origin" in
  git@github.com:rahi62/digitalafarin-platform.git|https://github.com/rahi62/digitalafarin-platform.git|https://github.com/rahi62/digitalafarin-platform) ;;
  *) fail "unexpected production repository origin" ;;
esac

before="$(git rev-parse HEAD)"
[[ "$before" =~ ^[0-9a-f]{40}$ ]] || fail "unable to resolve current commit"
printf 'Current commit: %s\nTarget commit:  %s\n' "$before" "$COMMIT"

git fetch --no-tags origin "$COMMIT"
resolved="$(git rev-parse FETCH_HEAD)"
[[ "$resolved" == "$COMMIT" ]] || fail "fetched commit does not match requested commit"

# Refuse to overwrite local production edits.
git diff --quiet && git diff --cached --quiet || fail "production repository has local changes"

git checkout --detach "$COMMIT"

# Reuse existing virtualenvs; credentials remain in /etc and are never copied into Git.
apps/api/.venv/bin/pip install -r apps/api/requirements.txt
agent/.venv/bin/pip install -e ./agent
mcp/.venv/bin/pip install -e ./mcp

# Validate schema before touching the running API.
(
  cd apps/api
  .venv/bin/python manage.py check
  .venv/bin/python manage.py makemigrations --check --dry-run
  .venv/bin/python manage.py migrate --noinput
)

# Build the web application before restarting any production service.
(
  cd apps/web
  npm ci
  npm test
  npm run lint
  npm run build
)

# Install reviewed unit definitions. Do not mutate tunnel ownership/handoff here.
install -m 0644 infra/systemd/digitalafarin-platform-api.service /etc/systemd/system/digitalafarin-platform-api.service
install -m 0644 infra/systemd/digitalafarin-platform-agent.service /etc/systemd/system/digitalafarin-platform-agent.service
install -m 0644 infra/systemd/digitalafarin-platform-mcp.service /etc/systemd/system/digitalafarin-platform-mcp.service
install -m 0644 infra/systemd/digitalafarin-platform-web.service /etc/systemd/system/digitalafarin-platform-web.service
install -m 0644 infra/systemd/digitalafarin-platform-takeover-helper.service /etc/systemd/system/digitalafarin-platform-takeover-helper.service
systemctl daemon-reload

# Helper first so the new Agent never talks to the old privileged protocol.
systemctl restart digitalafarin-platform-takeover-helper
systemctl restart digitalafarin-platform-api
systemctl restart digitalafarin-platform-agent
systemctl restart digitalafarin-platform-mcp
systemctl restart digitalafarin-platform-web

for unit in   digitalafarin-platform-takeover-helper   digitalafarin-platform-api   digitalafarin-platform-agent   digitalafarin-platform-mcp   digitalafarin-platform-web
do
  systemctl is-active --quiet "$unit" || fail "$unit is not active"
done

curl --fail --silent --show-error http://127.0.0.1:9750/health/ >/dev/null
[[ "$(git rev-parse HEAD)" == "$COMMIT" ]] || fail "production HEAD changed unexpectedly"
printf 'Platform bootstrap upgrade succeeded at %s\n' "$COMMIT"
