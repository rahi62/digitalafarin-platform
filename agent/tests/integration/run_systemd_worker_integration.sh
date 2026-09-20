#!/bin/sh
set -eu

repo=${1:-/opt/digitalafarin-platform}
user=${2:-deploy}
group=${3:-www-data}
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
probe="$project_root/agent/tests/integration/systemd_worker_probe.py"
suffix=$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')
unit="digitalafarin-takeover-integration-helper-$suffix.service"

test "$(ps -p 1 -o comm=)" = systemd
test "$(id -u)" -eq 0
getent passwd "$user" >/dev/null
getent group "$group" >/dev/null
test -d "$repo/.git"

cleanup() {
    systemctl stop "$unit" >/dev/null 2>&1 || true
    systemctl reset-failed "$unit" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

PYTHONPATH="$project_root/agent" /usr/bin/systemd-run \
    --quiet \
    --wait \
    --collect \
    --pipe \
    --unit="$unit" \
    --property=Type=oneshot \
    --property=User=root \
    --property=Group=digitalafarin-agent \
    --property=NoNewPrivileges=yes \
    --property=PrivateTmp=yes \
    --property=ProtectHome=yes \
    --property=ProtectSystem=strict \
    --property=ProtectKernelTunables=yes \
    --property=ProtectKernelModules=yes \
    --property=ProtectControlGroups=yes \
    --property=LockPersonality=yes \
    --setenv="PYTHONPATH=$project_root/agent" \
    -- \
    /usr/bin/python3 "$probe" --repo "$repo" --user "$user" --group "$group"

if systemctl list-units --all --plain --no-legend \
    'digitalafarin-takeover-worker-*.service' "$unit" | grep -q .; then
    echo "transient integration units were not collected" >&2
    exit 1
fi
