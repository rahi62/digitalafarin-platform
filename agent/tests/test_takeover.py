from pathlib import Path
from types import SimpleNamespace

import pytest

from digitalafarin_agent.takeover import (
    TakeoverExecutionError,
    prepare_service_takeover,
)


def prepare_payload():
    return {
        "takeover_id": "11111111-1111-1111-1111-111111111111",
        "service_id": "22222222-2222-2222-2222-222222222222",
        "project_slug": "digitalafarin-platform",
        "service_name": "platform-web",
        "unit_name": "digitalafarin-platform-web.service",
        "repository": "https://github.com/example/platform.git",
        "exact_commit": "a" * 40,
        "runtime": "node-nextjs",
        "root_directory": "apps/web",
        "install_configuration": {
            "package_manager": "npm",
            "lockfile": "package-lock.json",
        },
        "build_configuration": {"build_script": "build"},
        "service_port": 9751,
        "health_check": {
            "url": "http://127.0.0.1:9751/",
            "expected_status": 200,
            "attempts": 6,
            "timeout_seconds": 10,
            "interval_seconds": 5,
        },
    }


def snapshot(user="deploy"):
    return {
        "unit_name": "digitalafarin-platform-web.service",
        "fragment_path": "/etc/systemd/system/digitalafarin-platform-web.service",
        "drop_in_paths": [],
        "user": user,
        "group": "www-data",
        "working_directory": "/opt/digitalafarin-platform/apps/web",
        "exec_start_path": "/usr/bin/npm",
        "exec_start_argv": [
            "/usr/bin/npm",
            "start",
            "--",
            "--hostname",
            "127.0.0.1",
            "--port",
            "9751",
        ],
        "environment_file_paths": ["/etc/digitalafarin-platform/web.env"],
        "restart_policy": "on-failure",
        "restart_delay_usec": 3_000_000,
        "source_file_hashes": [
            {
                "path": "/etc/systemd/system/digitalafarin-platform-web.service",
                "sha256": "1" * 64,
            }
        ],
    }


def test_prepare_builds_release_as_source_user_without_activation(tmp_path, monkeypatch):
    calls = []
    release = (
        tmp_path
        / "apps"
        / "digitalafarin-platform"
        / "platform-web"
        / "releases"
        / "20260920-120000-aaaaaaa"
    )
    (release / "apps" / "web" / ".next").mkdir(parents=True)
    (release / "apps" / "web" / "package.json").write_text("{}", encoding="utf-8")
    (release / "apps" / "web" / "package-lock.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.fingerprint_snapshot", lambda _snapshot: "2" * 64
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._account",
        lambda user: SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_dir="/home/deploy"),
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._ensure_release_directories",
        lambda *args, **kwargs: (
            tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
        ),
    )

    def fake_prepare(*_args, **kwargs):
        calls.append(("git_runner", kwargs["run_command"]))
        return release

    monkeypatch.setattr("digitalafarin_agent.takeover.prepare_release", fake_prepare)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.run_recipe_as_user",
        lambda user, commands, cwd: calls.append(("build", user, commands, cwd)),
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.managed_dropin_path",
        lambda _unit: tmp_path / "not-present.conf",
    )
    runtime_cache = release / "apps" / "web" / ".next" / "cache"
    runtime_cache.mkdir(parents=True)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._prepare_next_runtime_cache",
        lambda cwd, user, group: runtime_cache,
    )
    sealed = []
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._seal_release",
        lambda release_path, service_root, *, writable_paths=(): sealed.append(
            (release_path, service_root, writable_paths)
        ),
    )

    result = prepare_service_takeover(prepare_payload(), apps_root=tmp_path / "apps")

    assert result["final_state"] == "prepared"
    assert result["source_fingerprint"] == "2" * 64
    assert result["release_name"] == release.name
    assert calls[1][1] == "deploy"
    assert calls[1][3] == release / "apps" / "web"
    assert sealed == [
        (
            release,
            tmp_path / "apps" / "digitalafarin-platform" / "platform-web",
            (runtime_cache,),
        )
    ]
    assert not (tmp_path / "apps" / "digitalafarin-platform" / "platform-web" / "current").exists()


@pytest.mark.parametrize("user", ["", "root"])
def test_prepare_rejects_unsafe_source_user_before_build(tmp_path, monkeypatch, user):
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot(user=user)
    )
    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("build path must not run")

    monkeypatch.setattr("digitalafarin_agent.takeover.prepare_release", fail_if_called)

    with pytest.raises(TakeoverExecutionError) as exc:
        prepare_service_takeover(prepare_payload(), apps_root=tmp_path / "apps")

    assert exc.value.code == "source_user_unsafe"
    assert called is False


def test_prepare_rejects_existing_reserved_dropin_before_build(tmp_path, monkeypatch):
    dropin = tmp_path / "90-digitalafarin-managed.conf"
    dropin.write_text("owned-by-someone-else", encoding="utf-8")
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._account",
        lambda user: SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_dir="/home/deploy"),
    )
    monkeypatch.setattr("digitalafarin_agent.takeover.managed_dropin_path", lambda _unit: dropin)

    with pytest.raises(TakeoverExecutionError) as exc:
        prepare_service_takeover(prepare_payload(), apps_root=tmp_path / "apps")

    assert exc.value.code == "managed_dropin_conflict"


def test_prepare_rejects_root_directory_escape(tmp_path, monkeypatch):
    payload = prepare_payload()
    payload["root_directory"] = "../outside"
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._account",
        lambda user: SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_dir="/home/deploy"),
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._ensure_release_directories",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.managed_dropin_path",
        lambda _unit: tmp_path / "not-present.conf",
    )
    release = (
        tmp_path / "apps" / "digitalafarin-platform" / "platform-web" / "releases" / "20260920-120000-aaaaaaa"
    )
    release.mkdir(parents=True)
    monkeypatch.setattr("digitalafarin_agent.takeover.prepare_release", lambda *args, **kwargs: release)

    with pytest.raises(TakeoverExecutionError) as exc:
        prepare_service_takeover(payload, apps_root=tmp_path / "apps")

    assert exc.value.code == "release_validation_failed"


def activate_payload():
    return {
        "takeover_id": "11111111-1111-1111-1111-111111111111",
        "service_id": "22222222-2222-2222-2222-222222222222",
        "project_slug": "digitalafarin-platform",
        "service_name": "platform-web",
        "unit_name": "digitalafarin-platform-web.service",
        "exact_commit": "a" * 40,
        "root_directory": "apps/web",
        "source_fingerprint": "a" * 64,
        "release_name": "20260920-120000-aaaaaaa",
        "release_path": (
            "/srv/digitalafarin/apps/digitalafarin-platform/"
            "platform-web/releases/20260920-120000-aaaaaaa"
        ),
        "health_check": prepare_payload()["health_check"],
    }


def make_activation_release(tmp_path):
    root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    release = root / "releases" / "20260920-120000-aaaaaaa"
    (release / "apps" / "web" / ".next").mkdir(parents=True)
    return root, release


def activate_payload_for(tmp_path):
    payload = activate_payload()
    _root, release = make_activation_release(tmp_path)
    payload["release_path"] = str(release.resolve())
    return payload


def test_activate_blocks_fingerprint_drift_before_mutation(tmp_path, monkeypatch):
    from digitalafarin_agent.takeover import activate_service_takeover

    payload = activate_payload_for(tmp_path)
    root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.fingerprint_snapshot", lambda _snapshot: "b" * 64
    )
    mutated = []
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.atomic_activate",
        lambda *_args, **_kwargs: mutated.append("current"),
    )

    with pytest.raises(TakeoverExecutionError) as exc:
        activate_service_takeover(payload, apps_root=tmp_path / "apps")

    assert exc.value.code == "service_configuration_changed"
    assert mutated == []
    assert not (root / "current").exists()


def test_activate_rejects_current_symlink_outside_managed_releases(tmp_path, monkeypatch):
    from digitalafarin_agent.takeover import activate_service_takeover

    payload = activate_payload_for(tmp_path)
    root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "current").symlink_to(outside)
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.fingerprint_snapshot", lambda _snapshot: "a" * 64
    )

    with pytest.raises(TakeoverExecutionError) as exc:
        activate_service_takeover(payload, apps_root=tmp_path / "apps")

    assert exc.value.code == "takeover_activation_failed"
    assert (root / "current").resolve() == outside.resolve()


def test_first_takeover_health_failure_rolls_back_dropin_and_current(tmp_path, monkeypatch):
    from digitalafarin_agent.health import HealthCheckError
    from digitalafarin_agent.takeover import activate_service_takeover

    payload = activate_payload_for(tmp_path)
    root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    release = Path(payload["release_path"])
    systemd_root = tmp_path / "systemd"
    calls = []
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.fingerprint_snapshot", lambda _snapshot: "a" * 64
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._managed_dropin_path",
        lambda unit: systemd_root / f"{unit}.d" / "90-digitalafarin-managed.conf",
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._write_managed_dropin",
        lambda unit, working_directory: (
            (systemd_root / f"{unit}.d").mkdir(parents=True, exist_ok=True),
            (systemd_root / f"{unit}.d" / "90-digitalafarin-managed.conf").write_text(
                f"[Service]\nWorkingDirectory={working_directory}\n", encoding="utf-8"
            ),
            systemd_root / f"{unit}.d" / "90-digitalafarin-managed.conf",
        )[-1],
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._remove_managed_dropin",
        lambda unit: (systemd_root / f"{unit}.d" / "90-digitalafarin-managed.conf").unlink(missing_ok=True),
    )
    monkeypatch.setattr("digitalafarin_agent.takeover.daemon_reload", lambda: calls.append("reload"))
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.restart_takeover_unit",
        lambda unit: calls.append(("restart", unit)),
    )
    health_calls = 0

    def health(_spec):
        nonlocal health_calls
        health_calls += 1
        if health_calls == 1:
            raise HealthCheckError("new release unhealthy")
        return {"attempts": 2, "status": 200, "consecutive_successes": 2}

    monkeypatch.setattr("digitalafarin_agent.takeover.check_http_health_stable", health)

    result = activate_service_takeover(payload, apps_root=tmp_path / "apps")

    assert result["final_state"] == "rolled_back"
    assert not (root / "current").exists()
    assert not (systemd_root / "digitalafarin-platform-web.service.d" / "90-digitalafarin-managed.conf").exists()
    assert calls.count(("restart", "digitalafarin-platform-web.service")) == 2
    assert not release.exists()


def test_rollback_failure_never_reports_success(tmp_path, monkeypatch):
    from digitalafarin_agent.health import HealthCheckError
    from digitalafarin_agent.takeover import activate_service_takeover

    payload = activate_payload_for(tmp_path)
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.fingerprint_snapshot", lambda _snapshot: "a" * 64
    )
    monkeypatch.setattr("digitalafarin_agent.takeover._managed_dropin_path", lambda _u: tmp_path / "dropin")
    monkeypatch.setattr("digitalafarin_agent.takeover._write_managed_dropin", lambda *_a, **_k: tmp_path / "dropin")
    monkeypatch.setattr("digitalafarin_agent.takeover._remove_managed_dropin", lambda *_a, **_k: None)
    monkeypatch.setattr("digitalafarin_agent.takeover.daemon_reload", lambda: None)
    monkeypatch.setattr("digitalafarin_agent.takeover.restart_takeover_unit", lambda _u: None)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.check_http_health_stable",
        lambda _spec: (_ for _ in ()).throw(HealthCheckError("unhealthy")),
    )

    with pytest.raises(TakeoverExecutionError) as exc:
        activate_service_takeover(payload, apps_root=tmp_path / "apps")

    assert exc.value.code == "takeover_rollback_failed"


def test_activate_installs_dropin_against_current_not_exact_release(tmp_path, monkeypatch):
    from digitalafarin_agent.takeover import activate_service_takeover

    payload = activate_payload_for(tmp_path)
    root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    captured = []
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.fingerprint_snapshot", lambda _snapshot: "a" * 64
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._managed_dropin_path",
        lambda _unit: tmp_path / "systemd" / "90-digitalafarin-managed.conf",
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._write_managed_dropin",
        lambda _unit, working_directory: (
            captured.append(working_directory),
            tmp_path / "systemd" / "90-digitalafarin-managed.conf",
        )[-1],
    )
    monkeypatch.setattr("digitalafarin_agent.takeover.daemon_reload", lambda: None)
    monkeypatch.setattr("digitalafarin_agent.takeover.restart_takeover_unit", lambda _unit: None)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.check_http_health_stable",
        lambda _spec: {"attempts": 2, "status": 200, "consecutive_successes": 2},
    )

    result = activate_service_takeover(payload, apps_root=tmp_path / "apps")

    assert result["final_state"] == "succeeded"
    assert captured == [root / "current" / "apps" / "web"]


def test_seal_release_removes_write_bits_and_root_owns_tree(tmp_path, monkeypatch):
    from digitalafarin_agent.takeover import _seal_release

    service_root = tmp_path / "apps" / "platform" / "web"
    release = service_root / "releases" / "release-a"
    executable = release / "node_modules" / ".bin" / "next"
    normal = release / "apps" / "web" / "package.json"
    executable.parent.mkdir(parents=True)
    normal.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    normal.write_text("{}", encoding="utf-8")
    executable.chmod(0o755)
    normal.chmod(0o644)
    chowns = []
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.os.chown",
        lambda path, uid, gid, **_kwargs: chowns.append((Path(path), uid, gid)),
    )

    _seal_release(release, service_root)

    assert executable.stat().st_mode & 0o222 == 0
    assert executable.stat().st_mode & 0o111 != 0
    assert normal.stat().st_mode & 0o222 == 0
    assert any(path == release and uid == 0 and gid == 0 for path, uid, gid in chowns)


def test_seal_release_preserves_declared_next_runtime_cache_write_permissions(tmp_path, monkeypatch):
    from digitalafarin_agent.takeover import _seal_release

    service_root = tmp_path / "apps" / "platform" / "web"
    release = service_root / "releases" / "release-a"
    normal = release / "apps" / "web" / "package.json"
    cache = release / "apps" / "web" / ".next" / "cache"
    cache_file = cache / "fetch-cache" / "entry"
    normal.parent.mkdir(parents=True)
    cache_file.parent.mkdir(parents=True)
    normal.write_text("{}", encoding="utf-8")
    cache_file.write_text("cache", encoding="utf-8")
    normal.chmod(0o644)
    cache.chmod(0o750)
    cache_file.chmod(0o640)
    chowns = []
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.os.chown",
        lambda path, uid, gid, **_kwargs: chowns.append((Path(path), uid, gid)),
    )

    _seal_release(release, service_root, writable_paths=(cache,))

    assert normal.stat().st_mode & 0o222 == 0
    assert cache.stat().st_mode & 0o200 != 0
    assert cache_file.stat().st_mode & 0o200 != 0
    assert not any(path == cache and uid == 0 for path, uid, _gid in chowns)
    assert not any(path == cache_file and uid == 0 for path, uid, _gid in chowns)


def test_prepare_next_runtime_cache_creates_writable_service_owned_directory(tmp_path, monkeypatch):
    from digitalafarin_agent.takeover import _prepare_next_runtime_cache

    cwd = tmp_path / "release" / "apps" / "web"
    (cwd / ".next").mkdir(parents=True)
    chowns = []
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._account",
        lambda user: SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_dir="/home/deploy"),
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._group_id",
        lambda group, fallback_gid: 33,
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.os.chown",
        lambda path, uid, gid, **_kwargs: chowns.append((Path(path), uid, gid)),
    )

    cache = _prepare_next_runtime_cache(cwd, user="deploy", group="www-data")

    assert cache == cwd / ".next" / "cache"
    assert cache.is_dir()
    assert cache.stat().st_mode & 0o700 == 0o700
    assert chowns == [(cache, 1000, 33)]
