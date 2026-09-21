from pathlib import Path
from types import SimpleNamespace

import pytest

from digitalafarin_agent.takeover import (
    TakeoverExecutionError,
    activate_service_takeover,
    prepare_service_takeover,
)
from digitalafarin_agent.takeover_helper_client import TakeoverHelperError


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
            "/usr/bin/npm", "start", "--", "--hostname", "127.0.0.1", "--port", "9751"
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


class FakeHelper:
    def __init__(self, *, release: Path | None = None):
        self.release = release
        self.calls = []
        self.activation = {
            "previous_release_name": None,
            "previous_current_path": None,
            "managed_dropin_path": "/etc/systemd/system/digitalafarin-platform-web.service.d/90-digitalafarin-managed.conf",
        }
        self.rollback_error = None

    def prepare_node_nextjs_release(self, params):
        self.calls.append(("prepare", params))
        assert self.release is not None
        from digitalafarin_agent.takeover import fingerprint_snapshot
        return {
            "release_name": self.release.name,
            "release_path": str(self.release),
            "resolved_commit": params["exact_commit"],
            "source_snapshot": snapshot(),
            "source_fingerprint": fingerprint_snapshot(snapshot()),
        }

    def activate_release(self, params):
        self.calls.append(("activate", params))
        return dict(self.activation)

    def rollback_activation(self, params):
        self.calls.append(("rollback", params))
        if self.rollback_error:
            raise self.rollback_error
        return {"previous_release_name": params["previous_release_name"]}

    def cleanup_release(self, params):
        self.calls.append(("cleanup", params))
        return {"removed": True}


def _make_prepared_release(tmp_path):
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
    return release


def test_prepare_delegates_privileged_release_work_without_activation(tmp_path, monkeypatch):
    release = _make_prepared_release(tmp_path)
    helper = FakeHelper(release=release)
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.fingerprint_snapshot", lambda _snapshot: "2" * 64
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._account",
        lambda user: SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_dir="/home/deploy"),
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.managed_dropin_path",
        lambda _unit: tmp_path / "not-present.conf",
    )

    result = prepare_service_takeover(
        prepare_payload(), apps_root=tmp_path / "apps", helper_client=helper
    )

    assert result["final_state"] == "prepared"
    assert result["source_fingerprint"] == "2" * 64
    assert result["release_name"] == release.name
    assert [name for name, _params in helper.calls] == ["prepare"]
    params = helper.calls[0][1]
    assert params["user"] == "deploy"
    assert params["group"] == "www-data"
    assert params["unit_name"] == "digitalafarin-platform-web.service"
    assert not (tmp_path / "apps" / "digitalafarin-platform" / "platform-web" / "current").exists()


@pytest.mark.parametrize("user", ["", "root"])
def test_prepare_rejects_unsafe_source_user_before_helper(tmp_path, monkeypatch, user):
    helper = FakeHelper()
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot(user=user)
    )

    with pytest.raises(TakeoverExecutionError) as exc:
        prepare_service_takeover(
            prepare_payload(), apps_root=tmp_path / "apps", helper_client=helper
        )

    assert exc.value.code == "source_user_unsafe"
    assert helper.calls == []


def test_prepare_rejects_existing_reserved_dropin_before_helper(tmp_path, monkeypatch):
    dropin = tmp_path / "90-digitalafarin-managed.conf"
    dropin.write_text("foreign", encoding="utf-8")
    helper = FakeHelper()
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._account",
        lambda user: SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_dir="/home/deploy"),
    )
    monkeypatch.setattr("digitalafarin_agent.takeover.managed_dropin_path", lambda _unit: dropin)

    with pytest.raises(TakeoverExecutionError) as exc:
        prepare_service_takeover(
            prepare_payload(), apps_root=tmp_path / "apps", helper_client=helper
        )

    assert exc.value.code == "managed_dropin_conflict"
    assert helper.calls == []


def test_prepare_propagates_stable_helper_error(tmp_path, monkeypatch):
    class FailingHelper(FakeHelper):
        def prepare_node_nextjs_release(self, params):
            raise TakeoverHelperError("release_prepare_failed", "helper failed")

    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._account",
        lambda user: SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_dir="/home/deploy"),
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.managed_dropin_path",
        lambda _unit: tmp_path / "not-present.conf",
    )

    with pytest.raises(TakeoverExecutionError) as exc:
        prepare_service_takeover(
            prepare_payload(), apps_root=tmp_path / "apps", helper_client=FailingHelper()
        )
    assert exc.value.code == "release_prepare_failed"


def test_prepare_rejects_root_directory_escape_before_helper(tmp_path):
    payload = prepare_payload()
    payload["root_directory"] = "../outside"
    with pytest.raises(TakeoverExecutionError) as exc:
        prepare_service_takeover(payload, apps_root=tmp_path / "apps", helper_client=FakeHelper())
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
        "release_path": "/srv/digitalafarin/apps/digitalafarin-platform/platform-web/releases/20260920-120000-aaaaaaa",
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


def _activation_common(tmp_path, monkeypatch):
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.fingerprint_snapshot", lambda _snapshot: "a" * 64
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover._managed_dropin_path",
        lambda _unit: tmp_path / "systemd" / "90-digitalafarin-managed.conf",
    )


def test_activate_blocks_fingerprint_drift_before_helper(tmp_path, monkeypatch):
    payload = activate_payload_for(tmp_path)
    helper = FakeHelper()
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _unit: snapshot())
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.fingerprint_snapshot", lambda _snapshot: "b" * 64
    )

    with pytest.raises(TakeoverExecutionError) as exc:
        activate_service_takeover(payload, apps_root=tmp_path / "apps", helper_client=helper)

    assert exc.value.code == "service_configuration_changed"
    assert helper.calls == []


def test_activate_rejects_current_symlink_outside_managed_releases_before_helper(tmp_path, monkeypatch):
    payload = activate_payload_for(tmp_path)
    root = tmp_path / "apps" / "digitalafarin-platform" / "platform-web"
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "current").symlink_to(outside)
    helper = FakeHelper()
    _activation_common(tmp_path, monkeypatch)

    with pytest.raises(TakeoverExecutionError) as exc:
        activate_service_takeover(payload, apps_root=tmp_path / "apps", helper_client=helper)

    assert exc.value.code == "takeover_activation_failed"
    assert helper.calls == []


def test_first_takeover_health_failure_delegates_rollback_and_cleanup(tmp_path, monkeypatch):
    from digitalafarin_agent.health import HealthCheckError

    payload = activate_payload_for(tmp_path)
    helper = FakeHelper()
    _activation_common(tmp_path, monkeypatch)
    health_calls = 0

    def health(_spec):
        nonlocal health_calls
        health_calls += 1
        if health_calls == 1:
            raise HealthCheckError("new release unhealthy")
        return {"attempts": 2, "status": 200, "consecutive_successes": 2}

    monkeypatch.setattr("digitalafarin_agent.takeover.check_http_health_stable", health)
    result = activate_service_takeover(
        payload, apps_root=tmp_path / "apps", helper_client=helper
    )

    assert result["final_state"] == "rolled_back"
    assert [name for name, _params in helper.calls] == ["activate", "rollback", "cleanup"]
    assert helper.calls[1][1]["previous_release_name"] is None


def test_rollback_failure_never_reports_success(tmp_path, monkeypatch):
    from digitalafarin_agent.health import HealthCheckError

    payload = activate_payload_for(tmp_path)
    helper = FakeHelper()
    helper.rollback_error = TakeoverHelperError("takeover_rollback_failed", "failed")
    _activation_common(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.check_http_health_stable",
        lambda _spec: (_ for _ in ()).throw(HealthCheckError("unhealthy")),
    )

    with pytest.raises(TakeoverExecutionError) as exc:
        activate_service_takeover(payload, apps_root=tmp_path / "apps", helper_client=helper)
    assert exc.value.code == "takeover_rollback_failed"


def test_activate_sends_derived_identity_not_arbitrary_working_directory(tmp_path, monkeypatch):
    payload = activate_payload_for(tmp_path)
    helper = FakeHelper()
    _activation_common(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover.check_http_health_stable",
        lambda _spec: {"attempts": 2, "status": 200, "consecutive_successes": 2},
    )

    result = activate_service_takeover(
        payload, apps_root=tmp_path / "apps", helper_client=helper
    )

    assert result["final_state"] == "succeeded"
    params = helper.calls[0][1]
    assert set(params) == {
        "project_slug",
        "service_name",
        "unit_name",
        "release_name",
        "root_directory",
        "source_fingerprint",
    }
    assert "working_directory" not in params
    assert "release_path" not in params


def test_prepare_never_accesses_filesystem_after_helper_success(tmp_path, monkeypatch):
    from digitalafarin_agent.takeover_systemd import fingerprint_snapshot

    release = tmp_path / "apps/digitalafarin-platform/platform-web/releases/20260920-120000-aaaaaaa"
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _u: snapshot())
    monkeypatch.setattr("digitalafarin_agent.takeover._account", lambda _u: SimpleNamespace(pw_uid=1000))
    dropin = tmp_path / "not-present.conf"
    monkeypatch.setattr("digitalafarin_agent.takeover.managed_dropin_path", lambda _u: dropin)

    def forbidden(*args, **kwargs):
        raise AssertionError("Agent accessed filesystem after Helper success")

    with pytest.MonkeyPatch.context() as guard:
        class SealedHelper:
            def prepare_node_nextjs_release(self, params):
                for method in ("resolve", "stat", "lstat", "exists", "is_dir", "is_file", "is_symlink", "open", "iterdir"):
                    guard.setattr(Path, method, forbidden)
                return {
                    "release_name": release.name,
                    "release_path": str(release),
                    "resolved_commit": "a" * 40,
                    "source_snapshot": snapshot(),
                    "source_fingerprint": fingerprint_snapshot(snapshot()),
                }

        result = prepare_service_takeover(
            prepare_payload(), apps_root=tmp_path / "apps", helper_client=SealedHelper()
        )
    assert result["final_state"] == "prepared"
    assert result["resolved_commit"] == "a" * 40
    assert not (release.parent.parent / "current").exists()
    assert not dropin.exists()


@pytest.mark.parametrize("field,value", [
    ("release_name", "../escape"),
    ("release_path", "/outside/release"),
    ("release_path", "/srv/digitalafarin/apps/../outside"),
    ("resolved_commit", "b" * 40),
    ("resolved_commit", "A" * 40),
    ("resolved_commit", None),
    ("source_snapshot", {}),
    ("source_fingerprint", "bad"),
])
def test_prepare_rejects_invalid_helper_metadata(tmp_path, monkeypatch, field, value):
    release = _make_prepared_release(tmp_path)
    class InvalidHelper(FakeHelper):
        def prepare_node_nextjs_release(self, params):
            result = super().prepare_node_nextjs_release(params)
            result[field] = value
            return result
    monkeypatch.setattr("digitalafarin_agent.takeover.inspect_service", lambda _u: snapshot())
    monkeypatch.setattr("digitalafarin_agent.takeover._account", lambda _u: SimpleNamespace(pw_uid=1000))
    monkeypatch.setattr("digitalafarin_agent.takeover.managed_dropin_path", lambda _u: tmp_path / "absent")
    with pytest.raises(TakeoverExecutionError) as exc:
        prepare_service_takeover(prepare_payload(), apps_root=tmp_path / "apps", helper_client=InvalidHelper(release=release))
    assert exc.value.code == "release_validation_failed"
