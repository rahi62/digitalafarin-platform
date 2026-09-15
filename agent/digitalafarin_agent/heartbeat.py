import asyncio
import logging
import socket

from digitalafarin_agent import __version__
from digitalafarin_agent.metrics import collect_metrics
from digitalafarin_agent.operations import OperationRunner
from digitalafarin_agent.systemd import list_services

logger = logging.getLogger(__name__)

_METRIC_KEYS = (
    "cpu_percent",
    "memory_percent",
    "disk_percent",
    "uptime_seconds",
)


def build_heartbeat_payload(
    hostname: str | None = None,
    agent_version: str = __version__,
) -> dict:
    collected = collect_metrics()
    metrics = {key: collected[key] for key in _METRIC_KEYS}
    return {
        "agent_version": agent_version,
        "hostname": hostname or socket.gethostname(),
        "capabilities": ["metrics", "systemd_inventory"],
        "metrics": metrics,
        "services": list_services(),
    }


class HeartbeatRunner:
    def __init__(
        self,
        *,
        client,
        identity_store,
        enrollment_token: str | None,
        agent_name: str,
        interval_seconds: int,
    ):
        self.client = client
        self.identity_store = identity_store
        self.enrollment_token = enrollment_token
        self.agent_name = agent_name
        self.interval_seconds = max(5, interval_seconds)

    async def ensure_identity(self) -> str:
        token = self.identity_store.read()
        if token:
            return token
        if not self.enrollment_token:
            raise RuntimeError(
                "agent is not enrolled and no enrollment token is configured"
            )
        result = await self.client.enroll(
            self.enrollment_token,
            {
                "name": self.agent_name,
                "hostname": socket.gethostname(),
                "agent_version": __version__,
                "capabilities": ["metrics", "systemd_inventory"],
            },
        )
        self.identity_store.write(result.agent_token)
        return result.agent_token

    async def run_forever(self) -> None:
        token = await self.ensure_identity()
        operation_runner = OperationRunner(self.client)
        while True:
            try:
                await self.client.heartbeat(token, build_heartbeat_payload())
                await operation_runner.run_once(token)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Never log HTTP payloads, headers, or bearer values.
                logger.warning("heartbeat failed: %s", type(exc).__name__)
            await asyncio.sleep(self.interval_seconds)
