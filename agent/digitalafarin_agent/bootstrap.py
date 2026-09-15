import os
import platform
import shutil
from pathlib import Path

import psutil


TOOLS = ("git", "python3", "node", "psql", "nginx", "systemctl")
SUPPORTED_OS = {"ubuntu", "debian"}


class BootstrapError(RuntimeError):
    pass


def _check(name: str, status: str, detail: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail}


def bootstrap_server(payload: dict, *, srv_root: Path = Path("/srv")) -> dict:
    if payload:
        raise BootstrapError("bootstrap accepts no caller configuration")
    base = (srv_root.resolve() / "digitalafarin").resolve()
    base.mkdir(parents=True, exist_ok=True)
    checks = []

    os_release = platform.freedesktop_os_release()
    os_id = os_release.get("ID", "")
    checks.append(_check("os", "ready" if os_id in SUPPORTED_OS else "blocked", os_id))

    disk = shutil.disk_usage(base)
    disk_percent = (disk.used / disk.total * 100) if disk.total else 100
    disk_status = "blocked" if disk_percent >= 90 else "warning" if disk_percent >= 80 else "ready"
    checks.append(_check("disk", disk_status, f"{disk_percent:.1f}%"))

    memory_bytes = psutil.virtual_memory().total
    checks.append(_check("memory", "ready" if memory_bytes >= 1024**3 else "warning", str(memory_bytes)))
    for tool in TOOLS:
        checks.append(_check(tool, "ready" if shutil.which(tool) else "blocked"))

    for name in ("apps", "volumes", "backups"):
        path = base / name
        path.mkdir(mode=0o750, parents=True, exist_ok=True)
        os.chmod(path, 0o750)
        checks.append(_check(f"directory.{name}", "ready", str(path)))

    statuses = {item["status"] for item in checks}
    overall = "blocked" if "blocked" in statuses else "warning" if "warning" in statuses else "ready"
    return {"overall": overall, "checks": checks}
