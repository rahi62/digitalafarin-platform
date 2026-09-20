import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path


SAFE_UNIT = re.compile(r"^[A-Za-z0-9_.@:-]+\.service$")
MANAGED_DROPIN_NAME = "90-digitalafarin-managed.conf"
SYSTEMD_ROOT = Path("/etc/systemd/system")
APPS_ROOT = Path("/srv/digitalafarin/apps")


class TakeoverSystemdError(RuntimeError):
    pass


def _validate_unit(unit_name: str) -> str:
    if not isinstance(unit_name, str) or not SAFE_UNIT.fullmatch(unit_name):
        raise TakeoverSystemdError("invalid systemd unit")
    return unit_name


def _read_hash(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TakeoverSystemdError(f"unable to read systemd source: {path}") from exc
    return hashlib.sha256(data).hexdigest()


def _parse_properties(stdout: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for raw in stdout.splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        props[key] = value
    return props


def _parse_exec_start(value: str) -> tuple[str, list[str]]:
    path_match = re.search(r"(?:^|[ {;])path=([^ ;}]+)", value)
    argv_match = re.search(r"(?:^|[ {;])argv\[\]=(.*?)(?:\s;|\s*})", value)
    if not path_match or not argv_match:
        raise TakeoverSystemdError("unsupported ExecStart representation")
    path = path_match.group(1)
    try:
        argv = shlex.split(argv_match.group(1).strip())
    except ValueError as exc:
        raise TakeoverSystemdError("invalid ExecStart argv") from exc
    if not argv:
        raise TakeoverSystemdError("missing ExecStart argv")
    return path, argv


def _parse_environment_files(value: str) -> list[str]:
    if not value.strip():
        return []
    paths = re.findall(r"(/[^\s]+)\s+\(ignore_errors=(?:yes|no)\)", value)
    if not paths:
        raise TakeoverSystemdError("unsupported EnvironmentFiles representation")
    return paths


def _parse_duration_usec(value: str) -> int:
    value = value.strip()
    if value.isdigit():
        return int(value)
    units = {
        "us": 1,
        "ms": 1_000,
        "s": 1_000_000,
        "min": 60_000_000,
    }
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(us|ms|s|min)", value)
    if not match:
        raise TakeoverSystemdError("unsupported restart delay")
    return int(float(match.group(1)) * units[match.group(2)])


def inspect_service(
    unit_name: str,
    *,
    fragment_override: Path | None = None,
) -> dict:
    unit_name = _validate_unit(unit_name)
    try:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                unit_name,
                "--property=FragmentPath",
                "--property=DropInPaths",
                "--property=User",
                "--property=Group",
                "--property=WorkingDirectory",
                "--property=ExecStart",
                "--property=EnvironmentFiles",
                "--property=Restart",
                "--property=RestartUSec",
                "--no-pager",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise TakeoverSystemdError("unable to inspect systemd unit") from exc

    props = _parse_properties(result.stdout)
    required = {
        "FragmentPath",
        "DropInPaths",
        "User",
        "Group",
        "WorkingDirectory",
        "ExecStart",
        "EnvironmentFiles",
        "Restart",
        "RestartUSec",
    }
    if not required.issubset(props):
        raise TakeoverSystemdError("incomplete systemd inspection")

    fragment_path = props["FragmentPath"].strip()
    if not fragment_path.startswith("/"):
        raise TakeoverSystemdError("invalid systemd fragment path")
    fragment_for_hash = fragment_override or Path(fragment_path)
    if fragment_override is None and not fragment_for_hash.is_file():
        raise TakeoverSystemdError("systemd fragment is not a file")

    try:
        drop_ins = shlex.split(props["DropInPaths"])
    except ValueError as exc:
        raise TakeoverSystemdError("invalid systemd drop-in list") from exc
    for item in drop_ins:
        if not item.startswith("/"):
            raise TakeoverSystemdError("invalid systemd drop-in path")
        if fragment_override is None and not Path(item).is_file():
            raise TakeoverSystemdError("systemd drop-in is not a file")

    exec_path, exec_argv = _parse_exec_start(props["ExecStart"])
    environment_files = _parse_environment_files(props["EnvironmentFiles"])
    hash_entries = [
        {"path": fragment_path, "sha256": _read_hash(fragment_for_hash)}
    ]
    for item in sorted(drop_ins):
        hash_entries.append({"path": item, "sha256": _read_hash(Path(item))})

    return {
        "unit_name": unit_name,
        "fragment_path": fragment_path,
        "drop_in_paths": sorted(drop_ins),
        "user": props["User"].strip(),
        "group": props["Group"].strip(),
        "working_directory": props["WorkingDirectory"].strip(),
        "exec_start_path": exec_path,
        "exec_start_argv": exec_argv,
        "environment_file_paths": environment_files,
        "restart_policy": props["Restart"].strip(),
        "restart_delay_usec": _parse_duration_usec(props["RestartUSec"]),
        "source_file_hashes": hash_entries,
    }


def fingerprint_snapshot(snapshot: dict) -> str:
    canonical = json.dumps(
        snapshot,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def managed_dropin_path(
    unit_name: str,
    *,
    systemd_root: Path = SYSTEMD_ROOT,
) -> Path:
    unit_name = _validate_unit(unit_name)
    root = systemd_root.resolve()
    path = root / f"{unit_name}.d" / MANAGED_DROPIN_NAME
    if not path.resolve(strict=False).is_relative_to(root):
        raise TakeoverSystemdError("managed drop-in path escapes systemd root")
    return path


def write_managed_dropin(
    unit_name: str,
    working_directory: Path,
    *,
    systemd_root: Path = SYSTEMD_ROOT,
    apps_root: Path = APPS_ROOT,
) -> Path:
    final = managed_dropin_path(unit_name, systemd_root=systemd_root)
    apps = apps_root.resolve()
    workdir = Path(working_directory)
    if (
        not workdir.is_absolute()
        or ".." in workdir.parts
        or not workdir.is_relative_to(apps)
    ):
        raise TakeoverSystemdError("managed working directory escapes apps root")
    if final.exists() or final.is_symlink():
        raise TakeoverSystemdError("managed drop-in already exists")
    final.parent.mkdir(parents=True, exist_ok=True)
    content = f"[Service]\nWorkingDirectory={workdir}\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{MANAGED_DROPIN_NAME}.",
        dir=final.parent,
        text=True,
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o644)
        if hasattr(os, "chown"):
            os.chown(tmp, 0, 0)
        os.replace(tmp, final)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
    return final


def remove_managed_dropin(
    unit_name: str,
    *,
    systemd_root: Path = SYSTEMD_ROOT,
) -> None:
    path = managed_dropin_path(unit_name, systemd_root=systemd_root)
    if path.exists() or path.is_symlink():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


def daemon_reload() -> None:
    try:
        subprocess.run(
            ["systemctl", "daemon-reload"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise TakeoverSystemdError("systemd daemon-reload failed") from exc


def restart_takeover_unit(unit_name: str) -> None:
    unit_name = _validate_unit(unit_name)
    try:
        subprocess.run(
            ["systemctl", "restart", unit_name],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise TakeoverSystemdError("takeover service restart failed") from exc
