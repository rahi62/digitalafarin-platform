import re
import subprocess

from .bootstrap import BootstrapError, bootstrap_server
from .postgres import DatabaseError, create_database, restore_database
from .redaction import redact
from .volumes import VolumeError, create_volume


UNIT_PATTERN = re.compile(r"^[A-Za-z0-9_.@:-]+\.service$")
PROTECTED_PREFIXES = (
    "digitalafarin-platform-",
    "digitalafarin-vps-mcp",
    "digitalafarin-telegram-mcp",
)
SERVICE_ACTIONS = {
    "service.start": "start",
    "service.stop": "stop",
    "service.restart": "restart",
}
MAX_LOG_BYTES = 65536


class OperationExecutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _validate_unit(payload: dict) -> str:
    allowed_keys = {"unit_name", "lines", "since_seconds"}
    if set(payload) - allowed_keys:
        raise OperationExecutionError("invalid_payload", "unsupported payload field")
    unit = payload.get("unit_name")
    if not isinstance(unit, str) or not UNIT_PATTERN.fullmatch(unit):
        raise OperationExecutionError("invalid_unit", "invalid service unit")
    if unit.startswith(PROTECTED_PREFIXES):
        raise OperationExecutionError("protected_unit", "service unit is protected")
    return unit


def _run(argv: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OperationExecutionError("execution_failed", type(exc).__name__) from exc
    if result.returncode != 0:
        message = redact(result.stderr or result.stdout or "command failed")[:500]
        raise OperationExecutionError("command_failed", message)
    return result


def _bounded(text: str) -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_LOG_BYTES:
        return text, False
    return encoded[:MAX_LOG_BYTES].decode("utf-8", errors="ignore"), True


def execute_operation(kind: str, payload: dict) -> dict:
    if kind == "database.create":
        try:
            return create_database(payload)
        except DatabaseError as exc:
            raise OperationExecutionError("database_create_failed", str(exc)) from exc
    if kind == "database.restore":
        try:
            return restore_database(payload)
        except DatabaseError as exc:
            raise OperationExecutionError("database_restore_failed", str(exc)) from exc
    if kind == "server.bootstrap":
        try:
            return bootstrap_server(payload)
        except BootstrapError as exc:
            raise OperationExecutionError("bootstrap_failed", str(exc)) from exc
    if kind == "volume.create":
        try:
            return create_volume(payload)
        except VolumeError as exc:
            raise OperationExecutionError("volume_failed", str(exc)) from exc
    if kind in SERVICE_ACTIONS:
        unit = _validate_unit(payload)
        if set(payload) != {"unit_name"}:
            raise OperationExecutionError("invalid_payload", "unsupported payload field")
        _run(["systemctl", SERVICE_ACTIONS[kind], unit], timeout=30)
        return {"message": f"{kind} completed"}
    if kind == "service.logs":
        unit = _validate_unit(payload)
        lines = payload.get("lines", 100)
        since_seconds = payload.get("since_seconds", 3600)
        if not isinstance(lines, int) or not 1 <= lines <= 200:
            raise OperationExecutionError("invalid_payload", "lines out of bounds")
        if not isinstance(since_seconds, int) or not 60 <= since_seconds <= 86400:
            raise OperationExecutionError("invalid_payload", "since_seconds out of bounds")
        result = _run(
            [
                "journalctl",
                "--unit",
                unit,
                "--lines",
                str(lines),
                "--since",
                f"{since_seconds} seconds ago",
                "--no-pager",
                "--output",
                "short-iso",
            ],
            timeout=15,
        )
        logs, truncated = _bounded(redact(result.stdout))
        return {"logs": logs, "truncated": truncated}
    raise OperationExecutionError("unsupported_operation", "unsupported operation kind")


class OperationRunner:
    def __init__(self, client):
        self.client = client

    async def run_once(self, agent_token: str) -> bool:
        claimed = await self.client.claim_operation(agent_token)
        if claimed is None:
            return False
        operation = claimed["operation"]
        claim_token = claimed["claim_token"]
        operation_id = operation["id"]
        await self.client.start_operation(agent_token, operation_id, claim_token)
        try:
            result = execute_operation(
                operation["kind"], operation.get("execution", operation["payload"])
            )
            completion = {"succeeded": True, "result": result}
        except OperationExecutionError as exc:
            completion = {
                "succeeded": False,
                "error_code": exc.code,
                "error_message": redact(str(exc))[:500],
            }
        await self.client.complete_operation(
            agent_token, operation_id, claim_token, completion
        )
        return True
