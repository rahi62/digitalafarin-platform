from pathlib import Path
from types import SimpleNamespace

import pytest

from digitalafarin_agent.takeover_systemd import (
    TakeoverSystemdError,
    fingerprint_snapshot,
    inspect_service,
    managed_dropin_path,
)


def show_output(start_time: str, pid: str) -> str:
    return "\n".join(
        [
            "FragmentPath=/etc/systemd/system/digitalafarin-platform-web.service",
            "DropInPaths=",
            "User=deploy",
            "Group=www-data",
            "WorkingDirectory=/opt/digitalafarin-platform/apps/web",
            (
                "ExecStart={ path=/usr/bin/npm ; "
                "argv[]=/usr/bin/npm start -- --hostname 127.0.0.1 --port 9751 ; "
                f"ignore_errors=no ; start_time=[{start_time}] ; "
                f"stop_time=[n/a] ; pid={pid} ; code=(null) ; status=0/0 }}"
            ),
            "EnvironmentFiles=/etc/digitalafarin-platform/web.env (ignore_errors=no)",
            "Restart=on-failure",
            "RestartUSec=3s",
        ]
    )


def test_fingerprint_ignores_execstart_runtime_pid_and_start_time(tmp_path, monkeypatch):
    unit = tmp_path / "digitalafarin-platform-web.service"
    unit.write_text("[Service]\nExecStart=/usr/bin/npm start\n", encoding="utf-8")
    outputs = iter(
        [
            show_output("Sun 2026-09-20 15:18:27 +0330", "517797"),
            show_output("Sun 2026-09-20 16:00:00 +0330", "600001"),
        ]
    )

    def run(*_args, **_kwargs):
        return SimpleNamespace(stdout=next(outputs))

    monkeypatch.setattr("digitalafarin_agent.takeover_systemd.subprocess.run", run)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_systemd._read_hash", lambda path: "a" * 64
    )

    first = inspect_service(
        "digitalafarin-platform-web.service", fragment_override=unit
    )
    second = inspect_service(
        "digitalafarin-platform-web.service", fragment_override=unit
    )

    assert first["exec_start_path"] == "/usr/bin/npm"
    assert first["exec_start_argv"] == [
        "/usr/bin/npm",
        "start",
        "--",
        "--hostname",
        "127.0.0.1",
        "--port",
        "9751",
    ]
    assert fingerprint_snapshot(first) == fingerprint_snapshot(second)


def test_fingerprint_changes_when_source_file_hash_changes():
    base = {
        "unit_name": "digitalafarin-platform-web.service",
        "fragment_path": "/etc/systemd/system/digitalafarin-platform-web.service",
        "drop_in_paths": [],
        "user": "deploy",
        "group": "www-data",
        "working_directory": "/opt/app",
        "exec_start_path": "/usr/bin/npm",
        "exec_start_argv": ["/usr/bin/npm", "start"],
        "environment_file_paths": [],
        "restart_policy": "on-failure",
        "restart_delay_usec": 3_000_000,
        "source_file_hashes": [
            {"path": "/etc/systemd/system/unit.service", "sha256": "a" * 64}
        ],
    }
    changed = {
        **base,
        "source_file_hashes": [
            {"path": "/etc/systemd/system/unit.service", "sha256": "b" * 64}
        ],
    }
    assert fingerprint_snapshot(base) != fingerprint_snapshot(changed)


def test_managed_dropin_path_is_derived_from_valid_unit_only():
    assert managed_dropin_path("digitalafarin-platform-web.service") == Path(
        "/etc/systemd/system/digitalafarin-platform-web.service.d/"
        "90-digitalafarin-managed.conf"
    )
    with pytest.raises(TakeoverSystemdError):
        managed_dropin_path("../../etc/passwd")


def test_managed_dropin_preserves_current_symlink_path(tmp_path, monkeypatch):
    from digitalafarin_agent.takeover_systemd import write_managed_dropin

    apps = tmp_path / "apps"
    service_root = apps / "digitalafarin-platform" / "platform-web"
    release_web = service_root / "releases" / "release-a" / "apps" / "web"
    release_web.mkdir(parents=True)
    (service_root / "current").symlink_to(service_root / "releases" / "release-a")
    systemd_root = tmp_path / "systemd"
    monkeypatch.setattr("digitalafarin_agent.takeover_systemd.os.chown", lambda *_args: None)

    dropin = write_managed_dropin(
        "digitalafarin-platform-web.service",
        service_root / "current" / "apps" / "web",
        systemd_root=systemd_root,
        apps_root=apps,
    )

    assert dropin.read_text(encoding="utf-8") == (
        "[Service]\n"
        f"WorkingDirectory={service_root / 'current' / 'apps' / 'web'}\n"
    )


def test_managed_restart_allows_protected_unit_but_generic_restart_stays_blocked(monkeypatch):
    from digitalafarin_agent.executors.systemd import RecipeError, SystemdExecutor

    calls = []
    monkeypatch.setattr(
        "digitalafarin_agent.executors.systemd.subprocess.run",
        lambda argv, **_kwargs: calls.append(argv),
    )
    executor = SystemdExecutor()

    with pytest.raises(RecipeError):
        executor.restart("digitalafarin-platform-web.service")

    executor.restart_managed("digitalafarin-platform-web.service")
    assert calls == [["systemctl", "restart", "digitalafarin-platform-web.service"]]
