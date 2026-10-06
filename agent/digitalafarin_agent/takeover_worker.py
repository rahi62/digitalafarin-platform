import grp
import logging
import pwd
import secrets
import subprocess
from pathlib import Path

from .redaction import redact


SYSTEMD_RUN = "/usr/bin/systemd-run"
SYSTEMCTL = "/usr/bin/systemctl"
WORKER_PREFIX = "digitalafarin-takeover-worker-"
_LOG_TAIL_LIMIT = 2048
_LOGGER = logging.getLogger(__name__)


class TakeoverWorkerError(RuntimeError):
    pass


def _validated_identity(user: str, group: str) -> None:
    if not isinstance(user, str) or not user or user == "root":
        raise TakeoverWorkerError("Takeover worker identity is unsafe.")
    if not isinstance(group, str) or not group:
        raise TakeoverWorkerError("Takeover worker identity is unsafe.")
    try:
        pwd.getpwnam(user)
        grp.getgrnam(group)
    except KeyError as exc:
        raise TakeoverWorkerError("Takeover worker identity is unavailable.") from exc


def _safe_diagnostic(value: str) -> str:
    tail = str(value)[-_LOG_TAIL_LIMIT:]
    printable = "".join(character if character.isprintable() else " " for character in tail)
    return redact(printable)


def _cleanup_worker(unit_name: str) -> None:
    for action in ("stop", "reset-failed"):
        try:
            subprocess.run(
                [SYSTEMCTL, action, unit_name],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def run_takeover_worker(
    *,
    phase: str,
    user: str,
    group: str,
    argv: list[str],
    cwd: Path | None = None,
    writable_path: Path | None = None,
    npm_cache: bool = False,
    timeout: int = 900,
) -> str:
    _validated_identity(user, group)
    if not argv or not all(isinstance(item, str) and item for item in argv):
        raise TakeoverWorkerError("Takeover worker command is invalid.")
    if not isinstance(phase, str) or not phase or timeout <= 0:
        raise TakeoverWorkerError("Takeover worker configuration is invalid.")

    unit_name = f"{WORKER_PREFIX}{secrets.token_hex(8)}.service"
    command = [
        SYSTEMD_RUN,
        "--quiet",
        "--wait",
        "--collect",
        "--pipe",
        f"--unit={unit_name}",
        "--property=Type=oneshot",
        f"--property=User={user}",
        f"--property=Group={group}",
        "--property=SupplementaryGroups=",
        "--property=NoNewPrivileges=yes",
        "--property=PrivateUsers=yes",
        "--property=PrivateTmp=yes",
        "--property=ProtectHome=yes",
        "--property=ProtectSystem=strict",
        "--property=ProtectKernelTunables=yes",
        "--property=ProtectKernelModules=yes",
        "--property=ProtectControlGroups=yes",
        "--property=RestrictSUIDSGID=yes",
        "--property=LockPersonality=yes",
        "--property=CapabilityBoundingSet=",
        "--property=AmbientCapabilities=",
        "--setenv=HOME=/tmp",
        f"--setenv=USER={user}",
        f"--setenv=LOGNAME={user}",
        "--setenv=PATH=/usr/local/bin:/usr/bin:/bin",
        "--setenv=GIT_TERMINAL_PROMPT=0",
    ]
    if npm_cache:
        command.append("--setenv=NPM_CONFIG_CACHE=/tmp/.npm-digitalafarin-takeover")
    if cwd is not None:
        working_directory = cwd.resolve(strict=True)
        command.append(f"--working-directory={working_directory}")
    if writable_path is not None:
        if writable_path.is_symlink():
            raise TakeoverWorkerError("Takeover worker writable path is invalid.")
        writable = writable_path.resolve(strict=True)
        if not writable.is_dir():
            raise TakeoverWorkerError("Takeover worker writable path is invalid.")
        if cwd is not None and not working_directory.is_relative_to(writable):
            raise TakeoverWorkerError("Takeover worker working directory is invalid.")
        command.append(f"--property=ReadWritePaths={writable}")
    command.extend(["--", *argv])

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
        )
    except subprocess.TimeoutExpired as exc:
        _cleanup_worker(unit_name)
        _LOGGER.warning(
            "takeover worker failed phase=%s unit=%s status=timeout stderr=%s",
            phase,
            unit_name,
            _safe_diagnostic(exc.stderr or ""),
        )
        raise TakeoverWorkerError("Takeover worker command failed.") from exc
    except OSError as exc:
        _LOGGER.warning(
            "takeover worker failed phase=%s unit=%s status=launch_error stderr=%s",
            phase,
            unit_name,
            _safe_diagnostic(type(exc).__name__),
        )
        raise TakeoverWorkerError("Takeover worker command failed.") from exc
    if result.returncode != 0:
        _LOGGER.warning(
            "takeover worker failed phase=%s unit=%s status=%s stderr=%s",
            phase,
            unit_name,
            result.returncode,
            _safe_diagnostic(result.stderr),
        )
        raise TakeoverWorkerError("Takeover worker command failed.")
    return result.stdout.strip()
