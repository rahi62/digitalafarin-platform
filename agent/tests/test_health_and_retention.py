from pathlib import Path

import pytest

from digitalafarin_agent.deployment import DeploymentFailure, deploy_release
from digitalafarin_agent.health import HealthCheckError, check_http_health


def test_health_check_retries_bounded_attempts():
    statuses = iter([503, 503, 200])
    sleeps = []

    result = check_http_health(
        {"url": "http://127.0.0.1:8000/health", "expected_status": 200, "attempts": 3, "timeout_seconds": 1, "interval_seconds": 1},
        request=lambda url, timeout: next(statuses),
        sleep=sleeps.append,
    )

    assert result["attempts"] == 3
    assert sleeps == [1, 1]


def test_health_check_failure_is_bounded():
    with pytest.raises(HealthCheckError):
        check_http_health(
            {"url": "http://127.0.0.1:8000/health", "expected_status": 200, "attempts": 2, "timeout_seconds": 1, "interval_seconds": 0},
            request=lambda url, timeout: 503,
            sleep=lambda seconds: None,
        )


class FakeExecutor:
    def __init__(self):
        self.actions = []

    def recipe_commands(self, runtime, install_configuration, build_configuration, root_directory):
        return [["npm", "ci"], ["npm", "run", "build"]]

    def run_commands(self, commands, cwd, environment, known_secrets):
        self.actions.append(("build", tuple(tuple(item) for item in commands), cwd))

    def restart(self, unit_name):
        raise AssertionError("managed deployment must not use generic protected restart")

    def restart_managed(self, unit_name):
        self.actions.append(("restart", unit_name))


def test_failed_post_activation_health_rolls_back_without_rebuild(tmp_path, monkeypatch):
    service_root = tmp_path / "apps" / "oily" / "web"
    previous = service_root / "releases" / "previous"
    new = service_root / "releases" / "new"
    previous.mkdir(parents=True)
    new.mkdir()
    (service_root / "current").symlink_to(previous)
    executor = FakeExecutor()
    checks = iter([False, True])
    def health(_spec):
        if not next(checks):
            raise HealthCheckError("new failed")
        return {"attempts": 1}
    monkeypatch.setattr("digitalafarin_agent.deployment.prepare_release", lambda *args, **kwargs: new)
    monkeypatch.setattr("digitalafarin_agent.deployment.check_http_health", health)

    result = deploy_release(
        {
            "deployment_id": "deployment-id",
            "project_slug": "oily",
            "service_name": "web",
            "repository": "https://example.invalid/repo.git",
            "exact_commit": "a" * 40,
            "runtime": "node-nextjs",
            "install_configuration": {},
            "build_configuration": {},
            "root_directory": ".",
            "unit_name": "oily-web.service",
            "environment": {"SECRET": "sentinel-secret"},
            "volumes": [],
            "health_check": {"url": "http://127.0.0.1:3000/health", "expected_status": 200},
        },
        apps_root=tmp_path / "apps",
        executor=executor,
    )

    assert result["final_state"] == "rolled_back"
    assert (service_root / "current").resolve() == previous.resolve()
    assert [action[0] for action in executor.actions].count("build") == 1
    assert [event["state"] for event in result["events"]][-2:] == ["verifying", "rolled_back"]


def test_stable_health_requires_two_consecutive_successes():
    from digitalafarin_agent.health import check_http_health_stable

    statuses = iter([200, 500, 200, 200])
    sleeps = []
    result = check_http_health_stable(
        {
            "url": "http://127.0.0.1:9751/",
            "expected_status": 200,
            "attempts": 6,
            "timeout_seconds": 1,
            "interval_seconds": 5,
        },
        request=lambda _url, _timeout: next(statuses),
        sleep=lambda seconds: sleeps.append(seconds),
    )
    assert result["attempts"] == 4
    assert result["consecutive_successes"] == 2
    assert 1 in sleeps


def test_stable_health_fails_without_two_consecutive_successes():
    from digitalafarin_agent.health import HealthCheckError, check_http_health_stable

    statuses = iter([200, 500, 200, 500])
    with pytest.raises(HealthCheckError):
        check_http_health_stable(
            {
                "url": "http://127.0.0.1:9751/",
                "expected_status": 200,
                "attempts": 4,
                "timeout_seconds": 1,
                "interval_seconds": 0,
            },
            request=lambda _url, _timeout: next(statuses),
            sleep=lambda _seconds: None,
        )
