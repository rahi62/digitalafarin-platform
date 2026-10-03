from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from digitalafarin_agent.takeover_helper import (
    TakeoverHelperDomainError,
    activate_release,
    cleanup_release,
    dispatch_helper_operation,
    prepare_node_nextjs_release,
    rollback_activation,
    trusted_source_repositories_from_env,
    _allocate_takeover_release,
    _ensure_release_directories,
    _prepare_release_destination,
    _run_as_worker,
    _trusted_local_source_repository,
)
from digitalafarin_agent.takeover_worker import TakeoverWorkerError



ALLOWED_BINDINGS = {
    (
        "digitalafarin-platform",
        "platform-web",
        "digitalafarin-platform-web.service",
    )
}

def _account(_user):
    return SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_dir="/home/deploy")


def _prepare_params():
    return {
        "project_slug": "digitalafarin-platform",
        "unit_name": "digitalafarin-platform-web.service",
        "service_name": "platform-web",
        "repository": "https://github.com/rahi62/digitalafarin-platform.git",
        "exact_commit": "a" * 40,
        "root_directory": "apps/web",
        "install_configuration": {
            "package_manager": "npm",
            "lockfile": "package-lock.json",
        },
        "build_configuration": {"build_script": "build"},
        "user": "deploy",
        "group": "www-data",
    }


def _release_tree(tmp_path):
    service_root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    release = service_root / "releases" / "20260920-120000-aaaaaaa"
    cwd = release / "apps" / "web"
    (cwd / ".next" / "cache").mkdir(parents=True)
    (cwd / "package.json").write_text("{}", encoding="utf-8")
    (cwd / "package-lock.json").write_text("{}", encoding="utf-8")
    return service_root, release, cwd


def test_helper_derives_and_preallocates_empty_restrictive_release(tmp_path, monkeypatch):
    service_root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    releases = service_root / "releases"
    releases.mkdir(parents=True)
    releases.chmod(0o755)
    chowns = []
    monkeypatch.setattr("digitalafarin_agent.takeover_helper._account", _account)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._group_id", lambda _group, _fallback: 33
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.os.chown",
        lambda path, uid, gid, **_kwargs: chowns.append((Path(path), uid, gid)),
    )

    release = _allocate_takeover_release(
        service_root,
        "a" * 40,
        user="deploy",
        group="www-data",
        timestamp="20260920-120000",
    )

    assert release == releases / "20260920-120000-aaaaaaa"
    assert release.is_dir()
    assert list(release.iterdir()) == []
    assert stat.S_IMODE(release.stat().st_mode) == 0o750
    assert stat.S_IMODE(releases.stat().st_mode) & 0o022 == 0
    assert chowns == [(release, 1000, 33)]


def test_release_roots_allow_traversal_without_parent_write_access(tmp_path, monkeypatch):
    apps_root = tmp_path / "apps"
    apps_root.mkdir(mode=0o750)
    monkeypatch.setattr("digitalafarin_agent.takeover_helper._account", _account)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._group_id", lambda _group, _fallback: 33
    )
    monkeypatch.setattr("digitalafarin_agent.takeover_helper.os.chown", lambda *_a: None)

    service_root = _ensure_release_directories(
        apps_root,
        "digitalafarin-platform",
        "platform-web",
        user="deploy",
        group="www-data",
    )

    releases = service_root / "releases"
    assert stat.S_IMODE(apps_root.stat().st_mode) == 0o751
    assert stat.S_IMODE(releases.stat().st_mode) == 0o755
    assert stat.S_IMODE(releases.stat().st_mode) & 0o022 == 0


def test_helper_allocates_unique_release_without_widening_parent(tmp_path, monkeypatch):
    service_root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    releases = service_root / "releases"
    existing = releases / "20260920-120000-aaaaaaa"
    existing.mkdir(parents=True)
    releases.chmod(0o755)
    monkeypatch.setattr("digitalafarin_agent.takeover_helper._account", _account)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._group_id", lambda _group, _fallback: 33
    )
    monkeypatch.setattr("digitalafarin_agent.takeover_helper.os.chown", lambda *_a: None)

    release = _allocate_takeover_release(
        service_root,
        "a" * 40,
        user="deploy",
        group="www-data",
        timestamp="20260920-120000",
    )

    assert release.name == "20260920-120000-aaaaaaa-2"
    assert stat.S_IMODE(releases.stat().st_mode) == 0o755


@pytest.mark.parametrize("kind", ["outside", "symlink", "nonempty"])
def test_release_destination_rejects_escape_symlink_or_nonempty(kind, tmp_path, monkeypatch):
    service_root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    releases = service_root / "releases"
    releases.mkdir(parents=True)
    monkeypatch.setattr("digitalafarin_agent.takeover_helper._account", _account)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._group_id", lambda _group, _fallback: 33
    )
    monkeypatch.setattr("digitalafarin_agent.takeover_helper.os.chown", lambda *_a: None)
    destination = releases / "20260920-120000-aaaaaaa"
    if kind == "outside":
        destination = tmp_path / "outside" / "20260920-120000-aaaaaaa"
        destination.parent.mkdir()
    elif kind == "symlink":
        target = tmp_path / "target"
        target.mkdir()
        destination.symlink_to(target, target_is_directory=True)
    else:
        destination.mkdir()
        (destination / "unexpected").write_text("data", encoding="utf-8")

    with pytest.raises(TakeoverHelperDomainError):
        _prepare_release_destination(
            destination,
            service_root=service_root,
            user="deploy",
            group="www-data",
        )


def test_prepare_helper_derives_release_and_runs_build_as_service_user(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("digitalafarin_agent.takeover_helper._account", _account)
    monkeypatch.setattr("digitalafarin_agent.takeover_helper._group_id", lambda _g, fallback: 33)
    monkeypatch.setattr("digitalafarin_agent.takeover_helper.os.chown", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.inspect_service",
        lambda _unit: {"unit_name": _unit, "user": "deploy", "group": "www-data"},
    )

    service_root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    prepared = []
    trusted_source = tmp_path / "trusted-source"
    trusted_source.mkdir()
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._trusted_local_source_repository",
        lambda *_a, **_k: trusted_source,
    )

    def fake_prepare(*args, **kwargs):
        assert args[2] == str(trusted_source)
        release = kwargs["destination"]
        prepared.append(release)
        assert release.is_dir()
        assert list(release.iterdir()) == []
        kwargs["run_command"](
            ["git", "clone", "--no-checkout", "--", str(trusted_source), str(release)],
            timeout=300,
        )
        kwargs["run_command"](
            ["git", "-C", str(release), "checkout", "--detach", "a" * 40],
            timeout=300,
        )
        cwd = release / "apps" / "web"
        (cwd / ".next").mkdir(parents=True)
        (cwd / "package.json").write_text("{}", encoding="utf-8")
        (cwd / "package-lock.json").write_text("{}", encoding="utf-8")
        return release

    monkeypatch.setattr("digitalafarin_agent.takeover_helper.prepare_release", fake_prepare)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.SystemdExecutor.recipe_commands",
        lambda *_a, **_k: [["npm", "ci"], ["npm", "run", "build"]],
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._run_as_worker",
        lambda user, group, argv, **kwargs: calls.append(
            (user, group, argv, kwargs)
        ),
    )
    sealed = []
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._seal_release",
        lambda release_path, root, *, runtime_gid, writable_paths=(): sealed.append(
            (release_path, root, runtime_gid, writable_paths)
        ),
    )

    # This test isolates worker dispatch; sealed-filesystem validation has its
    # own real-tree regressions and privileged Linux integration probe.
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._validate_prepared_release",
        lambda *_a, **_k: "a" * 40,
    )
    result = prepare_node_nextjs_release(_prepare_params(), allowed_bindings=ALLOWED_BINDINGS, apps_root=tmp_path / "apps")
    release = prepared[0]

    assert result["release_name"] == release.name
    assert result["release_path"] == str(release)
    assert result["resolved_commit"] == "a" * 40
    assert calls == [
        (
            "deploy",
            "www-data",
            ["git", "clone", "--no-checkout", "--", str(trusted_source), str(release)],
            {
                "writable_path": release,
                "phase": "release_git",
                "timeout": 300,
            },
        ),
        (
            "deploy",
            "www-data",
            ["git", "-C", str(release), "checkout", "--detach", "a" * 40],
            {
                "writable_path": release,
                "phase": "release_git",
                "timeout": 300,
            },
        ),
        (
            "deploy",
            "www-data",
            ["npm", "ci"],
            {
                "cwd": release / "apps" / "web",
                "writable_path": release,
                "phase": "npm_ci",
                "npm_cache": True,
                "timeout": 900,
            },
        ),
        (
            "deploy",
            "www-data",
            ["npm", "run", "build"],
            {
                "cwd": release / "apps" / "web",
                "writable_path": release,
                "phase": "next_build",
                "npm_cache": True,
                "timeout": 900,
            },
        ),
    ]
    assert sealed[0][0] == release
    assert sealed[0][1] == service_root
    assert sealed[0][2] == 33
    assert sealed[0][3] == (release / "apps" / "web" / ".next" / "cache",)


def test_prepare_helper_cleans_partial_release_when_build_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("digitalafarin_agent.takeover_helper._account", _account)
    monkeypatch.setattr("digitalafarin_agent.takeover_helper._group_id", lambda _g, fallback: 33)
    monkeypatch.setattr("digitalafarin_agent.takeover_helper.os.chown", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.inspect_service",
        lambda _unit: {"unit_name": _unit, "user": "deploy", "group": "www-data"},
    )
    trusted_source = tmp_path / "trusted-source-fail"
    trusted_source.mkdir()
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._trusted_local_source_repository",
        lambda *_a, **_k: trusted_source,
    )
    service_root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    prepared = []

    def fake_prepare(*_args, **kwargs):
        release = kwargs["destination"]
        prepared.append(release)
        assert release.is_dir()
        assert list(release.iterdir()) == []
        cwd = release / "apps" / "web"
        cwd.mkdir(parents=True)
        (cwd / "package.json").write_text("{}", encoding="utf-8")
        (cwd / "package-lock.json").write_text("{}", encoding="utf-8")
        return release

    monkeypatch.setattr("digitalafarin_agent.takeover_helper.prepare_release", fake_prepare)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.SystemdExecutor.recipe_commands",
        lambda *_a, **_k: [["npm", "ci"]],
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._run_as_worker",
        lambda *_a, **_k: (_ for _ in ()).throw(
            TakeoverHelperDomainError("release_prepare_failed", "build failed")
        ),
    )

    with pytest.raises(TakeoverHelperDomainError) as exc:
        prepare_node_nextjs_release(
            _prepare_params(),
            allowed_bindings=ALLOWED_BINDINGS,
            apps_root=tmp_path / "apps",
        )
    assert exc.value.code == "release_prepare_failed"
    release = prepared[0]
    assert not release.exists()


def test_prepare_helper_rejects_non_allowlisted_unit_before_mutation(tmp_path):
    params = _prepare_params()
    params["unit_name"] = "oily.service"
    with pytest.raises(TakeoverHelperDomainError) as exc:
        prepare_node_nextjs_release(
            params,
            allowed_bindings=ALLOWED_BINDINGS,
            apps_root=tmp_path / "apps",
        )
    assert exc.value.code == "helper_identity_not_allowed"
    assert not (tmp_path / "apps").exists()


def test_prepare_helper_rejects_local_or_credentialed_repository_before_mutation(tmp_path):
    for repository in (
        "file:///tmp/repo",
        "/tmp/repo",
        "https://user:secret@example.com/repo.git",
    ):
        params = _prepare_params()
        params["repository"] = repository
        with pytest.raises(TakeoverHelperDomainError) as exc:
            prepare_node_nextjs_release(params, allowed_bindings=ALLOWED_BINDINGS, apps_root=tmp_path / "apps")
        assert exc.value.code == "release_validation_failed"
    assert not (tmp_path / "apps").exists()


def test_prepare_helper_rejects_parent_path_root_directory_before_mutation(tmp_path):
    params = _prepare_params()
    params["root_directory"] = "../outside"
    with pytest.raises(TakeoverHelperDomainError) as exc:
        prepare_node_nextjs_release(params, allowed_bindings=ALLOWED_BINDINGS, apps_root=tmp_path / "apps")
    assert exc.value.code == "release_validation_failed"
    assert not (tmp_path / "apps").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("worker_unit_name", "evil.service"),
        ("command", "id"),
        ("argv", ["id"]),
        ("path", "/tmp/evil"),
        ("systemd_property", "ProtectSystem=false"),
    ],
)
def test_prepare_protocol_rejects_worker_control_fields_before_mutation(
    field, value, tmp_path
):
    params = _prepare_params()
    params[field] = value

    with pytest.raises(TakeoverHelperDomainError) as exc:
        prepare_node_nextjs_release(
            params,
            allowed_bindings=ALLOWED_BINDINGS,
            apps_root=tmp_path / "apps",
        )

    assert exc.value.code == "helper_invalid_request"
    assert not (tmp_path / "apps").exists()



def test_source_verification_uses_systemd_worker_with_service_identity(tmp_path, monkeypatch):
    calls = []
    def worker(**kwargs):
        calls.append(kwargs)
        argv = kwargs["argv"]
        if argv[-3:] == ["remote", "get-url", "origin"]:
            return "https://github.com/rahi62/digitalafarin-platform.git"
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return "a" * 40
        return ""
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.run_takeover_worker",
        worker,
    )
    source = tmp_path / "trusted-source"
    source.mkdir()

    output = _trusted_local_source_repository(
        "digitalafarin-platform",
        "platform-web",
        "digitalafarin-platform-web.service",
        "a" * 40,
        "https://github.com/rahi62/digitalafarin-platform.git",
        "deploy",
        "www-data",
        {ALLOWED_BINDINGS.copy().pop(): source},
    )

    assert output == source
    assert [call["phase"] for call in calls] == [
        "source_verify",
        "source_sync",
        "source_sync",
        "source_verify",
    ]
    assert calls[0]["argv"] == ["git", "-C", str(source), "remote", "get-url", "origin"]
    assert calls[1]["argv"] == ["git", "-C", str(source), "fetch", "--no-tags", "origin", "a" * 40]
    assert calls[2]["argv"] == ["git", "-C", str(source), "checkout", "--detach", "a" * 40]
    assert calls[3]["argv"] == ["git", "-C", str(source), "rev-parse", "HEAD"]


def test_trusted_source_repository_configuration_parses_exact_binding(monkeypatch):
    monkeypatch.setenv(
        "DIGITALAFARIN_TAKEOVER_SOURCE_REPOSITORIES",
        "digitalafarin-platform|platform-web|digitalafarin-platform-web.service|/opt/digitalafarin-platform",
    )
    assert trusted_source_repositories_from_env() == {
        (
            "digitalafarin-platform",
            "platform-web",
            "digitalafarin-platform-web.service",
        ): Path("/opt/digitalafarin-platform")
    }


def test_trusted_source_repository_requires_exact_production_head(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    def worker(**kwargs):
        argv = kwargs["argv"]
        if argv[-3:] == ["remote", "get-url", "origin"]:
            return "https://github.com/rahi62/digitalafarin-platform.git"
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return "b" * 40
        return ""
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.run_takeover_worker",
        worker,
    )
    with pytest.raises(TakeoverHelperDomainError) as exc:
        _trusted_local_source_repository(
            "digitalafarin-platform",
            "platform-web",
            "digitalafarin-platform-web.service",
            "a" * 40,
            "deploy",
            "www-data",
            {
                (
                    "digitalafarin-platform",
                    "platform-web",
                    "digitalafarin-platform-web.service",
                ): source
            },
        )
    assert exc.value.code == "source_sync_failed"


def test_worker_command_failure_maps_to_stable_helper_error(monkeypatch):
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.run_takeover_worker",
        lambda **_kwargs: (_ for _ in ()).throw(
            TakeoverWorkerError("internal diagnostic")
        ),
    )

    with pytest.raises(TakeoverHelperDomainError) as exc:
        _run_as_worker(
            "deploy",
            "www-data",
            ["npm", "ci"],
            phase="npm_ci",
        )

    assert exc.value.code == "release_prepare_failed"
    assert str(exc.value) == "Takeover build command failed."
    assert "internal diagnostic" not in str(exc.value)


def test_trusted_source_repository_rejects_missing_binding():
    with pytest.raises(TakeoverHelperDomainError) as exc:
        _trusted_local_source_repository(
            "digitalafarin-platform",
            "platform-web",
            "digitalafarin-platform-web.service",
            "a" * 40,
            "deploy",
            "www-data",
            {},
        )
    assert exc.value.code == "helper_configuration_error"


def _activate_params():
    return {
        "project_slug": "digitalafarin-platform",
        "service_name": "platform-web",
        "unit_name": "digitalafarin-platform-web.service",
        "release_name": "20260920-120000-aaaaaaa",
        "root_directory": "apps/web",
        "source_fingerprint": "a" * 64,
        "exact_commit": "a" * 40,
    }


def _stub_systemd(monkeypatch, systemd_root, calls):
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.inspect_service",
        lambda _unit: {"unit_name": "digitalafarin-platform-web.service"},
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.fingerprint_snapshot",
        lambda _snapshot: "a" * 64,
    )

    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._validate_prepared_release",
        lambda _release, _service_root, _root_directory, exact_commit, _install, *, sealed: exact_commit
        if sealed
        else (_ for _ in ()).throw(AssertionError("activation must validate sealed release")),
    )

    def write(unit, working_directory, **_kwargs):
        path = systemd_root / f"{unit}.d" / "90-digitalafarin-managed.conf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"[Service]\nWorkingDirectory={working_directory}\n", encoding="utf-8")
        calls.append(("write", unit, working_directory))
        return path

    def remove(unit, **_kwargs):
        path = systemd_root / f"{unit}.d" / "90-digitalafarin-managed.conf"
        path.unlink(missing_ok=True)
        calls.append(("remove", unit))

    monkeypatch.setattr("digitalafarin_agent.takeover_helper.write_managed_dropin", write)
    monkeypatch.setattr("digitalafarin_agent.takeover_helper.remove_managed_dropin", remove)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.daemon_reload", lambda: calls.append("reload")
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.restart_takeover_unit",
        lambda unit: calls.append(("restart", unit)),
    )


def test_activate_helper_rechecks_fingerprint_before_mutation(tmp_path, monkeypatch):
    _service_root, release, _cwd = _release_tree(tmp_path)
    calls = []
    systemd_root = tmp_path / "systemd"
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.inspect_service", lambda _unit: {}
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.fingerprint_snapshot",
        lambda _snapshot: "b" * 64,
    )

    with pytest.raises(TakeoverHelperDomainError) as exc:
        activate_release(
            _activate_params(),
            allowed_bindings=ALLOWED_BINDINGS,
            apps_root=tmp_path / "apps",
            systemd_root=systemd_root,
        )
    assert exc.value.code == "service_configuration_changed"
    assert not (release.parent.parent / "current").exists()
    assert calls == []


def test_activate_helper_rejects_non_allowlisted_unit_before_mutation(tmp_path):
    _release_tree(tmp_path)
    params = _activate_params()
    params["unit_name"] = "oily.service"
    with pytest.raises(TakeoverHelperDomainError) as exc:
        activate_release(
            params,
            allowed_bindings=ALLOWED_BINDINGS,
            apps_root=tmp_path / "apps",
            systemd_root=tmp_path / "systemd",
        )
    assert exc.value.code == "helper_identity_not_allowed"


def test_activate_helper_rolls_back_if_current_changes_during_atomic_switch(tmp_path, monkeypatch):
    service_root, release, _cwd = _release_tree(tmp_path)
    previous = service_root / "releases" / "20260919-120000-bbbbbbb"
    (previous / "apps" / "web" / ".next").mkdir(parents=True)
    calls = []
    systemd_root = tmp_path / "systemd"
    _stub_systemd(monkeypatch, systemd_root, calls)

    def racy_activate(root, target):
        current = root / "current"
        if current.exists() or current.is_symlink():
            current.unlink()
        current.symlink_to(target)
        return previous

    monkeypatch.setattr("digitalafarin_agent.takeover_helper.atomic_activate", racy_activate)

    with pytest.raises(TakeoverHelperDomainError) as exc:
        activate_release(
            _activate_params(),
            allowed_bindings=ALLOWED_BINDINGS,
            apps_root=tmp_path / "apps",
            systemd_root=systemd_root,
        )
    assert exc.value.code == "takeover_activation_failed"
    assert not (service_root / "current").exists()


def test_activate_helper_revalidates_sealed_release_before_mutation(tmp_path, monkeypatch):
    service_root, release, _cwd = _release_tree(tmp_path)
    calls = []
    systemd_root = tmp_path / "systemd"
    _stub_systemd(monkeypatch, systemd_root, calls)
    validated = {}

    def validate(candidate, root, root_directory, exact_commit, install, *, sealed):
        validated.update(
            candidate=candidate,
            root=root,
            root_directory=root_directory,
            exact_commit=exact_commit,
            install=install,
            sealed=sealed,
        )
        return exact_commit

    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._validate_prepared_release", validate
    )

    result = activate_release(
        _activate_params(),
        allowed_bindings=ALLOWED_BINDINGS,
        apps_root=tmp_path / "apps",
        systemd_root=systemd_root,
    )

    assert result["previous_release_name"] is None
    assert validated == {
        "candidate": release.resolve(),
        "root": service_root.resolve(),
        "root_directory": "apps/web",
        "exact_commit": "a" * 40,
        "install": {"lockfile": "package-lock.json"},
        "sealed": True,
    }


def test_activate_helper_rejects_invalid_sealed_release_before_mutation(tmp_path, monkeypatch):
    service_root, _release, _cwd = _release_tree(tmp_path)
    calls = []
    systemd_root = tmp_path / "systemd"
    _stub_systemd(monkeypatch, systemd_root, calls)

    def reject(*_args, **_kwargs):
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Prepared release failed privileged validation."
        )

    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._validate_prepared_release", reject
    )

    with pytest.raises(TakeoverHelperDomainError) as exc:
        activate_release(
            _activate_params(),
            allowed_bindings=ALLOWED_BINDINGS,
            apps_root=tmp_path / "apps",
            systemd_root=systemd_root,
        )

    assert exc.value.code == "release_validation_failed"
    assert not (service_root / "current").exists()
    assert calls == []


def test_activate_and_rollback_helper_only_mutate_derived_current_and_dropin(tmp_path, monkeypatch):
    service_root, release, _cwd = _release_tree(tmp_path)
    calls = []
    systemd_root = tmp_path / "systemd"
    _stub_systemd(monkeypatch, systemd_root, calls)

    result = activate_release(
        _activate_params(),
        allowed_bindings=ALLOWED_BINDINGS,
        apps_root=tmp_path / "apps",
        systemd_root=systemd_root,
    )

    assert (service_root / "current").resolve() == release.resolve()
    assert result["previous_release_name"] is None
    assert calls[0] == (
        "write",
        "digitalafarin-platform-web.service",
        service_root / "current" / "apps" / "web",
    )
    assert calls[-1] == ("restart", "digitalafarin-platform-web.service")

    rollback_activation(
        {
            "project_slug": "digitalafarin-platform",
            "service_name": "platform-web",
            "unit_name": "digitalafarin-platform-web.service",
            "previous_release_name": None,
        },
        allowed_bindings=ALLOWED_BINDINGS,
        apps_root=tmp_path / "apps",
        systemd_root=systemd_root,
    )
    assert not (service_root / "current").exists()
    assert not (
        systemd_root
        / "digitalafarin-platform-web.service.d"
        / "90-digitalafarin-managed.conf"
    ).exists()


def test_cleanup_helper_refuses_active_release(tmp_path):
    service_root, release, _cwd = _release_tree(tmp_path)
    (service_root / "current").symlink_to(release)
    with pytest.raises(TakeoverHelperDomainError) as exc:
        cleanup_release(
            {
                "project_slug": "digitalafarin-platform",
                "service_name": "platform-web",
                "unit_name": "digitalafarin-platform-web.service",
                "release_name": release.name,
            },
            allowed_bindings=ALLOWED_BINDINGS,
            apps_root=tmp_path / "apps",
        )
    assert exc.value.code == "takeover_cleanup_failed"
    assert release.exists()


def test_prepare_helper_rejects_mismatched_service_identity_before_mutation(tmp_path):
    params = _prepare_params()
    params["project_slug"] = "oily"
    params["service_name"] = "web"
    with pytest.raises(TakeoverHelperDomainError) as exc:
        prepare_node_nextjs_release(
            params,
            allowed_bindings=ALLOWED_BINDINGS,
            apps_root=tmp_path / "apps",
        )
    assert exc.value.code == "helper_identity_not_allowed"
    assert not (tmp_path / "apps").exists()


def test_prepare_helper_rejects_user_group_drift_before_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr("digitalafarin_agent.takeover_helper._account", _account)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.inspect_service",
        lambda _unit: {"user": "unexpected", "group": "www-data"},
    )
    params = _prepare_params()
    with pytest.raises(TakeoverHelperDomainError) as exc:
        prepare_node_nextjs_release(
            params,
            allowed_bindings=ALLOWED_BINDINGS,
            apps_root=tmp_path / "apps",
        )
    assert exc.value.code == "service_configuration_changed"
    assert not (tmp_path / "apps").exists()


def test_cleanup_helper_cannot_target_non_allowlisted_service(tmp_path):
    oily_release = (
        tmp_path / "apps" / "oily" / "web" / "releases" / "20260920-120000-aaaaaaa"
    )
    oily_release.mkdir(parents=True)
    with pytest.raises(TakeoverHelperDomainError) as exc:
        cleanup_release(
            {
                "project_slug": "oily",
                "service_name": "web",
                "unit_name": "digitalafarin-platform-web.service",
                "release_name": oily_release.name,
            },
            allowed_bindings=ALLOWED_BINDINGS,
            apps_root=tmp_path / "apps",
        )
    assert exc.value.code == "helper_identity_not_allowed"
    assert oily_release.exists()


def test_dispatch_rejects_arbitrary_privileged_operation():
    with pytest.raises(TakeoverHelperDomainError) as exc:
        dispatch_helper_operation("run_shell", {"command": "id"}, allowed_bindings=set())
    assert exc.value.code == "helper_operation_not_allowed"



def test_seal_release_removes_write_bits_and_root_owns_tree(tmp_path, monkeypatch):
    from digitalafarin_agent.takeover_helper import _seal_release

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
        "digitalafarin_agent.takeover_helper.os.chown",
        lambda path, uid, gid, **_kwargs: chowns.append((Path(path), uid, gid)),
    )

    _seal_release(release, service_root, runtime_gid=33)

    assert executable.stat().st_mode & 0o222 == 0
    assert executable.stat().st_mode & 0o111 != 0
    assert normal.stat().st_mode & 0o222 == 0
    assert any(path == release and uid == 0 and gid == 33 for path, uid, gid in chowns)


def test_seal_release_preserves_declared_next_runtime_cache_write_permissions(tmp_path, monkeypatch):
    from digitalafarin_agent.takeover_helper import _seal_release

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
        "digitalafarin_agent.takeover_helper.os.chown",
        lambda path, uid, gid, **_kwargs: chowns.append((Path(path), uid, gid)),
    )

    _seal_release(release, service_root, runtime_gid=33, writable_paths=(cache,))

    assert normal.stat().st_mode & 0o222 == 0
    assert cache.stat().st_mode & 0o200 != 0
    assert cache_file.stat().st_mode & 0o200 != 0
    assert not any(path == cache and uid == 0 for path, uid, _gid in chowns)
    assert not any(path == cache_file and uid == 0 for path, uid, _gid in chowns)


def test_prepare_next_runtime_cache_creates_writable_service_owned_directory(tmp_path, monkeypatch):
    from digitalafarin_agent.takeover_helper import _prepare_next_runtime_cache

    cwd = tmp_path / "release" / "apps" / "web"
    (cwd / ".next").mkdir(parents=True)
    chowns = []
    monkeypatch.setattr("digitalafarin_agent.takeover_helper._account", _account)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper._group_id", lambda _group, _fallback: 33
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_helper.os.chown",
        lambda path, uid, gid, **_kwargs: chowns.append((Path(path), uid, gid)),
    )

    cache = _prepare_next_runtime_cache(cwd, user="deploy", group="www-data")

    assert cache == cwd / ".next" / "cache"
    assert cache.is_dir()
    assert cache.stat().st_mode & 0o700 == 0o700
    assert chowns == [(cache, 1000, 33)]
