from types import SimpleNamespace

import pytest

from digitalafarin_agent.operations import (
    OperationExecutionError,
    OperationRunner,
    execute_operation,
)


def completed(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def test_restart_uses_exact_systemctl_argv(monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return completed()

    monkeypatch.setattr("digitalafarin_agent.operations.subprocess.run", run)

    result = execute_operation(
        "service.restart", {"unit_name": "oily-api.service"}
    )

    assert result == {"message": "service.restart completed"}
    assert calls[0][0] == ["systemctl", "restart", "oily-api.service"]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["timeout"] == 30


@pytest.mark.parametrize(
    "kind,unit",
    [
        ("shell.execute", "oily-api.service"),
        ("service.restart", "digitalafarin-platform-agent.service"),
        ("service.start", "../../etc/passwd"),
    ],
)
def test_execution_rejects_untyped_protected_or_invalid_work(kind, unit):
    with pytest.raises(OperationExecutionError):
        execute_operation(kind, {"unit_name": unit})


def test_logs_are_bounded_and_redacted(monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return completed(stdout="Authorization: Bearer secret-token\n" + "x" * 70000)

    monkeypatch.setattr("digitalafarin_agent.operations.subprocess.run", run)

    result = execute_operation(
        "service.logs",
        {"unit_name": "oily-api.service", "lines": 200, "since_seconds": 3600},
    )

    assert calls[0] == [
        "journalctl",
        "--unit",
        "oily-api.service",
        "--lines",
        "200",
        "--since",
        "3600 seconds ago",
        "--no-pager",
        "--output",
        "short-iso",
    ]
    assert "secret-token" not in result["logs"]
    assert len(result["logs"].encode()) <= 65536
    assert result["truncated"] is True


class FakeClient:
    def __init__(self):
        self.calls = []

    async def claim_operation(self, token):
        self.calls.append("claim")
        return {
            "operation": {
                "id": "11111111-1111-1111-1111-111111111111",
                "kind": "service.stop",
                "payload": {"unit_name": "oily-api.service"},
            },
            "claim_token": "claim-token",
        }

    async def start_operation(self, token, operation_id, claim_token):
        self.calls.append("started")

    async def complete_operation(self, token, operation_id, claim_token, payload):
        self.calls.append(("complete", payload))


@pytest.mark.asyncio
async def test_runner_reports_claim_started_and_complete_in_order(monkeypatch):
    monkeypatch.setattr(
        "digitalafarin_agent.operations.execute_operation",
        lambda kind, payload: {"message": f"{kind} done"},
    )
    client = FakeClient()

    worked = await OperationRunner(client).run_once("agent-token")

    assert worked is True
    assert client.calls[0:2] == ["claim", "started"]
    assert client.calls[2][0] == "complete"
    assert client.calls[2][1]["succeeded"] is True


@pytest.mark.asyncio
async def test_runner_converts_unexpected_executor_error_to_safe_failed_completion(monkeypatch):
    def fail(_kind, _payload):
        raise PermissionError("/srv/digitalafarin/private-secret")

    monkeypatch.setattr("digitalafarin_agent.operations.execute_operation", fail)
    client = FakeClient()

    worked = await OperationRunner(client).run_once("agent-token")

    assert worked is True
    completion = client.calls[2][1]
    assert completion["succeeded"] is False
    assert completion["error_code"] == "execution_failed"
    assert completion["error_message"] == "PermissionError"
    assert "private-secret" not in str(completion)


def test_takeover_prepare_uses_dedicated_executor_and_generic_protection_remains(monkeypatch):
    monkeypatch.setattr(
        "digitalafarin_agent.operations.prepare_service_takeover",
        lambda payload: {
            "takeover_id": payload["takeover_id"],
            "final_state": "prepared",
        },
    )

    result = execute_operation(
        "service.takeover.prepare",
        {"takeover_id": "11111111-1111-1111-1111-111111111111"},
    )
    assert result["final_state"] == "prepared"

    with pytest.raises(OperationExecutionError) as exc:
        execute_operation(
            "service.restart",
            {"unit_name": "digitalafarin-platform-web.service"},
        )
    assert exc.value.code == "protected_unit"


def test_service_delete_uses_privileged_helper_with_fixed_identity(monkeypatch):
    calls = []
    class Helper:
        def delete_managed_service(self, params):
            calls.append(params)
            return {"managed_artifacts_removed": True, "unit_deleted": False}
    monkeypatch.setattr("digitalafarin_agent.operations.TakeoverHelperClient", lambda: Helper())
    result = execute_operation("service.delete", {
        "service_id": "11111111-1111-1111-1111-111111111111",
        "project_slug": "oily",
        "service_name": "web",
        "unit_name": "oily-web.service",
        "root_directory": ".",
    })
    assert result["managed_artifacts_removed"] is True
    assert calls == [{
        "project_slug": "oily",
        "service_name": "web",
        "unit_name": "oily-web.service",
        "root_directory": ".",
    }]


def test_service_delete_rejects_protected_platform_unit_before_helper(monkeypatch):
    monkeypatch.setattr(
        "digitalafarin_agent.operations.TakeoverHelperClient",
        lambda: (_ for _ in ()).throw(AssertionError("helper must not be called")),
    )
    with pytest.raises(OperationExecutionError) as exc:
        execute_operation("service.delete", {
            "service_id": "11111111-1111-1111-1111-111111111111",
            "project_slug": "digitalafarin-platform",
            "service_name": "web",
            "unit_name": "digitalafarin-platform-web.service",
            "root_directory": ".",
        })
    assert exc.value.code == "protected_unit"
