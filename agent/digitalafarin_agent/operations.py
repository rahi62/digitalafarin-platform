import asyncio
import logging
import re
import subprocess
from contextlib import suppress
from .progress import reporter

from .bootstrap import BootstrapError, bootstrap_server
from .postgres import DatabaseError, create_database, restore_database
from .deployment import DeploymentFailure, deploy_managed_release, rollback_managed_release
from .domains import DomainError, configure_domain, enable_ssl
from .redaction import redact
from .takeover import TakeoverExecutionError, activate_service_takeover, prepare_service_takeover
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
    if kind == "service.takeover.prepare":
        try:
            return prepare_service_takeover(payload)
        except TakeoverExecutionError as exc:
            raise OperationExecutionError(exc.code, str(exc)) from exc
    if kind == "service.takeover.activate":
        try:
            return activate_service_takeover(payload)
        except TakeoverExecutionError as exc:
            raise OperationExecutionError(exc.code, str(exc)) from exc
    if kind == "domain.configure":
        try:
            return configure_domain(payload)
        except DomainError as exc:
            raise OperationExecutionError("domain_configure_failed", str(exc)) from exc
    if kind == "domain.ssl":
        try:
            return enable_ssl(payload)
        except DomainError as exc:
            raise OperationExecutionError("domain_ssl_failed", str(exc)) from exc
    if kind == "deployment.deploy":
        try:
            result = deploy_managed_release(payload)
            if result["final_state"] == "failed":
                code = result["error_code"]
                raise OperationExecutionError(code, code)
            return result
        except Exception as exc:
            if isinstance(exc, OperationExecutionError):
                raise
            raise OperationExecutionError("deployment_failed", redact(str(exc))[:500]) from exc
    if kind == "deployment.rollback":
        try:
            result = rollback_managed_release(payload)
            if result["final_state"] == "failed":
                code = result["error_code"]
                raise OperationExecutionError(code, code)
            return result
        except Exception as exc:
            if isinstance(exc, OperationExecutionError):
                raise
            raise OperationExecutionError("rollback_failed", redact(str(exc))[:500]) from exc
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
    def __init__(self, client, *, journal=None):
        self.client = client
        self.journal = journal
        self.pending = journal.read() if journal else None

    def _save(self, record):
        if self.journal:
            self.journal.write(record)
        self.pending = record

    async def _deliver(self, agent_token):
        record = self.pending
        if 'completion' not in record:
            # An interrupted process may have mutated the host. Never replay it
            # on a timer; surface uncertainty for inspection/reconciliation.
            await self.client.start_operation(agent_token, record['operation_id'], record['claim_token'])
            self._save({**record, 'completion': {
                'succeeded': False, 'error_code': 'execution_interrupted',
                'error_message': 'Agent restarted during execution; inspect host state before retrying.',
            }})
            record = self.pending
        await self.client.complete_operation(
            agent_token, record['operation_id'], record['claim_token'], record['completion'],
        )
        if self.journal:
            self.journal.clear()
        self.pending = None

    async def run_forever(self, agent_token, *, interval_seconds=5):
        while True:
            try:
                await self.run_once(agent_token)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logging.getLogger(__name__).warning('operation delivery failed: %s', type(exc).__name__)
            await asyncio.sleep(interval_seconds)

    async def run_once(self, agent_token: str) -> bool:
        if self.pending is not None:
            await self._deliver(agent_token)
            return True
        claimed = await self.client.claim_operation(agent_token)
        if claimed is None:
            return False
        operation = claimed["operation"]
        claim_token = claimed["claim_token"]
        operation_id = operation["id"]
        record = {'operation_id': operation_id, 'claim_token': claim_token}
        self._save(record)
        await self.client.start_operation(agent_token, operation_id, claim_token)
        stage = ['running']
        context = reporter.set(lambda value: stage.__setitem__(0, value))
        async def renew():
            sequence = 0
            while True:
                sequence += 1
                try:
                    await self.client.progress_operation(agent_token, operation_id, claim_token, sequence, stage[0])
                except Exception as exc:
                    logging.getLogger(__name__).warning('progress delivery failed: %s', type(exc).__name__)
                await asyncio.sleep(15)
        renewal = asyncio.create_task(renew()) if hasattr(self.client, 'progress_operation') else None
        try:
            result = await asyncio.to_thread(execute_operation,
                operation["kind"], operation.get("execution", operation["payload"])
            )
            completion = {"succeeded": True, "result": result}
        except OperationExecutionError as exc:
            completion = {
                "succeeded": False,
                "error_code": exc.code,
                "error_message": redact(str(exc))[:500],
            }
        except Exception as exc:
            completion = {
                "succeeded": False,
                "error_code": "execution_failed",
                "error_message": type(exc).__name__,
            }
        finally:
            reporter.reset(context)
            if renewal:
                renewal.cancel()
                with suppress(asyncio.CancelledError):
                    await renewal
        self._save({**record, 'completion': completion})
        await self._deliver(agent_token)
        return True
