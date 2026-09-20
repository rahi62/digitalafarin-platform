import os
import re
from pathlib import Path

from .executors.systemd import SystemdExecutor
from .health import HealthCheckError, check_http_health
from .releases import atomic_activate, cleanup_releases, prepare_release, resolve_exact_commit, rollback


SAFE_ROOT = re.compile(r"^(?:\.|[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)$")


class DeploymentFailure(RuntimeError):
    pass


def _event(events: list[dict], state: str, message: str = "") -> None:
    events.append({"state": state, "message": message})


def _write_environment(release: Path, values: dict[str, str]) -> Path:
    path = release / ".digitalafarin.env"
    lines = []
    for key, value in sorted(values.items()):
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,127}", key):
            raise DeploymentFailure("invalid environment key")
        escaped = value.replace("\\", "\\\\").replace("\n", "\\n")
        lines.append(f"{key}={escaped}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def _attach_volumes(release: Path, volumes: list[dict]) -> None:
    for volume in volumes:
        mount = volume["mount_path"].lstrip("/")
        if not SAFE_ROOT.fullmatch(mount):
            raise DeploymentFailure("invalid volume mount path")
        target = release / mount
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                raise DeploymentFailure("volume mount target already exists")
            target.unlink()
        target.symlink_to(Path(volume["host_path"]))


def deploy_release(
    payload: dict,
    *,
    apps_root: Path = Path("/srv/digitalafarin/apps"),
    executor=None,
) -> dict:
    executor = executor or SystemdExecutor()
    events: list[dict] = []
    _event(events, "preparing")
    exact_commit = payload.get("exact_commit") or resolve_exact_commit(
        payload["repository"], payload["requested_ref"]
    )
    service_root = apps_root.resolve() / payload["project_slug"] / payload["service_name"]
    _event(events, "cloning")
    release = prepare_release(
        payload["project_slug"],
        payload["service_name"],
        payload["repository"],
        exact_commit,
        apps_root=apps_root,
    )
    _write_environment(release, payload.get("environment", {}))
    _attach_volumes(release, payload.get("volumes", []))
    root_directory = payload.get("root_directory", ".")
    if not SAFE_ROOT.fullmatch(root_directory):
        raise DeploymentFailure("invalid root directory")
    cwd = (release / root_directory).resolve()
    if not cwd.is_relative_to(release.resolve()):
        raise DeploymentFailure("root directory escapes release")
    commands = executor.recipe_commands(
        payload["runtime"],
        payload.get("install_configuration", {}),
        payload.get("build_configuration", {}),
        root_directory,
    )
    _event(events, "building")
    secrets = tuple(payload.get("environment", {}).values())
    executor.run_commands(commands, cwd, payload.get("environment", {}), secrets)
    _event(events, "releasing")
    _event(events, "health_check")
    _event(events, "activating")
    previous = atomic_activate(service_root, release)
    executor.restart_managed(payload["unit_name"])
    _event(events, "verifying")
    try:
        check_http_health(payload["health_check"])
    except HealthCheckError:
        if previous is None:
            raise DeploymentFailure("health check failed and no rollback release exists")
        rollback(service_root, previous)
        executor.restart_managed(payload["unit_name"])
        check_http_health(payload["health_check"])
        _event(events, "rolled_back", "New release failed health verification")
        return {
            "deployment_id": payload["deployment_id"],
            "final_state": "rolled_back",
            "release_name": release.name,
            "exact_commit": exact_commit,
            "events": events,
        }
    _event(events, "succeeded")
    cleanup_releases(service_root, keep=5, protected={release, previous} if previous else {release})
    return {
        "deployment_id": payload["deployment_id"],
        "final_state": "succeeded",
        "release_name": release.name,
        "exact_commit": exact_commit,
        "events": events,
    }


def rollback_release(payload: dict, *, executor=None) -> dict:
    executor = executor or SystemdExecutor()
    service_root = Path(payload["service_root"])
    release = Path(payload["release_path"])
    rollback(service_root, release)
    executor.restart_managed(payload["unit_name"])
    check_http_health(payload["health_check"])
    return {
        "deployment_id": payload["deployment_id"],
        "final_state": "succeeded",
        "release_name": release.name,
        "exact_commit": payload["exact_commit"],
        "events": [
            {"state": state, "message": "Rollback activation"}
            for state in (
                "preparing", "cloning", "building", "releasing", "health_check",
                "activating", "verifying", "succeeded",
            )
        ],
    }
