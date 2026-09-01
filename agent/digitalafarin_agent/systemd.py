import subprocess
from dataclasses import asdict, dataclass

from .config import get_settings


@dataclass(frozen=True)
class ServiceUnit:
    unit_name: str
    load_state: str
    active_state: str
    sub_state: str
    description: str


def parse_systemctl_list_units(output: str) -> list[ServiceUnit]:
    units: list[ServiceUnit] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        units.append(ServiceUnit(*parts))
    return units


def _is_allowed(unit_name: str, prefixes: tuple[str, ...]) -> bool:
    if "*" in prefixes:
        return True
    return any(unit_name.startswith(prefix) for prefix in prefixes)


def list_services() -> list[dict]:
    result = subprocess.run(
        [
            "systemctl",
            "list-units",
            "--type=service",
            "--all",
            "--no-legend",
            "--no-pager",
            "--plain",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=8,
    )
    prefixes = get_settings().service_prefixes
    return [
        asdict(unit)
        for unit in parse_systemctl_list_units(result.stdout)
        if _is_allowed(unit.unit_name, prefixes)
    ]
