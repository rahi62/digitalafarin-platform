from digitalafarin_agent.heartbeat import HeartbeatRunner, build_heartbeat_payload


def test_payload_contains_only_collected_metrics_and_allowlisted_services(monkeypatch):
    monkeypatch.setattr(
        "digitalafarin_agent.heartbeat.collect_metrics",
        lambda: {
            "cpu_percent": 10.0,
            "memory_percent": 20.0,
            "disk_percent": 30.0,
            "uptime_seconds": 40,
        },
    )
    monkeypatch.setattr(
        "digitalafarin_agent.heartbeat.list_services",
        lambda: [
            {
                "unit_name": "digitalafarin-platform-api.service",
                "description": "API",
                "load_state": "loaded",
                "active_state": "active",
                "sub_state": "running",
            }
        ],
    )

    payload = build_heartbeat_payload("host", "0.2.0")

    assert payload["hostname"] == "host"
    assert payload["services"][0]["unit_name"] == "digitalafarin-platform-api.service"
    assert set(payload["metrics"]) == {
        "cpu_percent",
        "memory_percent",
        "disk_percent",
        "uptime_seconds",
    }
    assert "token" not in str(payload).lower()


class MemoryIdentity:
    def __init__(self):
        self.value = None

    def read(self):
        return self.value

    def write(self, value):
        self.value = value


class FakeClient:
    def __init__(self):
        self.enroll_calls = 0

    async def enroll(self, enrollment_token, payload):
        from digitalafarin_agent.control_plane import EnrollmentResponse

        self.enroll_calls += 1
        return EnrollmentResponse("server-id", "da_agent_prefix.secret")


async def _identity_token():
    client = FakeClient()
    store = MemoryIdentity()
    runner = HeartbeatRunner(
        client=client,
        identity_store=store,
        enrollment_token="da_enroll_prefix.secret",
        agent_name="Primary",
        interval_seconds=15,
    )
    first = await runner.ensure_identity()
    second = await runner.ensure_identity()
    return client, store, first, second


def test_enrollment_token_is_exchanged_only_once():
    import asyncio

    client, store, first, second = asyncio.run(_identity_token())

    assert first == "da_agent_prefix.secret"
    assert second == first
    assert store.value == first
    assert client.enroll_calls == 1


def test_payload_advertises_typed_operation_and_bootstrap_capabilities(monkeypatch):
    monkeypatch.setattr(
        "digitalafarin_agent.heartbeat.collect_metrics",
        lambda: {
            "cpu_percent": 1.0,
            "memory_percent": 2.0,
            "disk_percent": 3.0,
            "uptime_seconds": 4,
        },
    )
    monkeypatch.setattr("digitalafarin_agent.heartbeat.list_services", lambda: [])

    payload = build_heartbeat_payload("host", "0.2.0")

    assert "typed_operations" in payload["capabilities"]
    assert "server_bootstrap" in payload["capabilities"]
    assert "takeover_helper_v1" in payload["capabilities"]
