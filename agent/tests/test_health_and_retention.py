import pytest

from digitalafarin_agent.deployment import deploy_release
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


@pytest.mark.parametrize('url', ['http://127.0.0.1:80@evil.test/', 'http://127.0.0.1:0/', 'http://127.0.0.1:3000/#fragment'])
def test_health_rejects_urls_that_only_look_like_loopback(url):
    with pytest.raises(HealthCheckError):
        check_http_health({'url': url}, request=lambda *_: pytest.fail('unsafe request'))


def test_failed_post_activation_health_rolls_back_without_rebuild(monkeypatch):
    actions = []
    class Helper:
        def prepare_managed_node_nextjs_release(self, params):
            actions.append("build")
            return {"release_name": "20260923-120000-aaaaaaa", "resolved_commit": "a" * 40}
        def activate_managed_release(self, params):
            actions.append("activate")
            return {"previous_release_name": "20260922-120000-bbbbbbb"}
        def rollback_managed_activation(self, params):
            actions.append("rollback")
            assert params["previous_release_name"] == "20260922-120000-bbbbbbb"
        def cleanup_release(self, params):
            actions.append("cleanup")
    checks = iter([False, True])
    def health(_spec):
        if not next(checks):
            raise HealthCheckError("new failed")
        return {"attempts": 1}
    monkeypatch.setattr("digitalafarin_agent.deployment.check_http_health", health)
    result = deploy_release(
        {
            "deployment_id": "deployment-id", "project_slug": "oily", "service_name": "web",
            "repository": "https://example.invalid/repo.git", "exact_commit": "a" * 40,
            "runtime": "node-nextjs", "unit_name": "oily-web.service", "environment": {},
            "volumes": [], "health_check": {"url": "http://127.0.0.1:3000/health"},
        }, helper=Helper(),
    )
    assert result["final_state"] == "rolled_back"
    assert actions == ["build", "activate", "rollback", "cleanup"]
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
