#!/bin/sh
set -eu

repo=${1:-/opt/digitalafarin-platform}
user=${2:-deploy}
group=${3:-www-data}
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
probe="$project_root/agent/tests/integration/systemd_worker_probe.py"
suffix=$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')
unit="digitalafarin-takeover-integration-helper-$suffix.service"
allocation_root="/srv/digitalafarin/apps/.takeover-worker-integration-$suffix"
managed_root=/srv/digitalafarin
apps_root="$managed_root/apps"

test "$(ps -p 1 -o comm=)" = systemd
test "$(id -u)" -eq 0
getent passwd "$user" >/dev/null
getent group "$group" >/dev/null
test -d "$repo/.git"
managed_root_mode=$(stat -c %a "$managed_root")
apps_root_mode=$(stat -c %a "$apps_root")
chmod 0751 "$managed_root" "$apps_root"
install -d -o root -g root -m 0755 "$allocation_root"

cleanup() {
    systemctl stop "$unit" >/dev/null 2>&1 || true
    systemctl reset-failed "$unit" >/dev/null 2>&1 || true
    rm -rf "$allocation_root"
    chmod "$apps_root_mode" "$apps_root"
    chmod "$managed_root_mode" "$managed_root"
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
    --property="ReadWritePaths=$allocation_root" \
    --setenv="PYTHONPATH=$project_root/agent" \
    -- \
    /usr/bin/python3 "$probe" --repo "$repo" --user "$user" --group "$group" \
    --allocation-root "$allocation_root"

if systemctl list-units --all --plain --no-legend \
    'digitalafarin-takeover-worker-*.service' "$unit" | grep -q .; then
    echo "transient integration units were not collected" >&2
    exit 1
fi
