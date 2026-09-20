import grp
import os
import pwd
import re
import stat
import subprocess
import uuid
from pathlib import Path

from .executors.systemd import RecipeError, SystemdExecutor
from .health import HealthCheckError, check_http_health_stable
from .releases import COMMIT, SLUG, ReleaseError, atomic_activate, prepare_release
from .takeover_systemd import (
    daemon_reload,
    fingerprint_snapshot,
    inspect_service,
    managed_dropin_path,
    remove_managed_dropin,
    restart_takeover_unit,
    write_managed_dropin,
)


SAFE_ROOT = re.compile(r"^(?:\.|[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)$")
_PREPARE_KEYS = {
    "takeover_id",
    "service_id",
    "project_slug",
    "service_name",
    "unit_name",
    "repository",
    "exact_commit",
    "runtime",
    "root_directory",
    "install_configuration",
    "build_configuration",
    "service_port",
    "health_check",
}

_ACTIVATE_KEYS = {
    "takeover_id",
    "service_id",
    "project_slug",
    "service_name",
    "unit_name",
    "exact_commit",
    "root_directory",
    "source_fingerprint",
    "release_name",
    "release_path",
    "health_check",
}


def _managed_dropin_path(unit_name: str) -> Path:
    return managed_dropin_path(unit_name)


def _write_managed_dropin(unit_name: str, working_directory: Path) -> Path:
    return write_managed_dropin(unit_name, working_directory)


def _remove_managed_dropin(unit_name: str) -> None:
    remove_managed_dropin(unit_name)


class TakeoverExecutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _account(user: str):
    if not user or user == "root":
        raise TakeoverExecutionError(
            "source_user_unsafe",
            "Takeover build requires a non-root source service user.",
        )
    try:
        return pwd.getpwnam(user)
    except KeyError as exc:
        raise TakeoverExecutionError(
            "source_user_unsafe",
            "Source service user does not exist.",
        ) from exc


def _group_id(group: str, fallback_gid: int) -> int:
    if not group:
        return fallback_gid
    try:
        return grp.getgrnam(group).gr_gid
    except KeyError:
        return fallback_gid


def run_as_user(
    user: str,
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 900,
) -> None:
    account = _account(user)
    if not argv or not all(isinstance(item, str) and item for item in argv):
        raise TakeoverExecutionError("release_prepare_failed", "Invalid build command.")
    try:
        result = subprocess.run(
            [
                "runuser",
                "-u",
                user,
                "--",
                "env",
                "-i",
                f"HOME={account.pw_dir}",
                f"USER={user}",
                f"LOGNAME={user}",
                "PATH=/usr/local/bin:/usr/bin:/bin",
                "GIT_TERMINAL_PROMPT=0",
                *argv,
            ],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TakeoverExecutionError(
            "release_prepare_failed", type(exc).__name__
        ) from exc
    if result.returncode != 0:
        raise TakeoverExecutionError(
            "release_prepare_failed",
            "Takeover build command failed.",
        )


def run_recipe_as_user(user: str, commands: list[list[str]], cwd: Path) -> None:
    for command in commands:
        run_as_user(user, command, cwd=cwd, timeout=900)


def _ensure_release_directories(
    apps_root: Path,
    project_slug: str,
    service_name: str,
    *,
    user: str,
    group: str,
) -> Path:
    account = _account(user)
    root = apps_root.resolve()
    service_root = (root / project_slug / service_name).resolve()
    if not service_root.is_relative_to(root):
        raise TakeoverExecutionError(
            "release_validation_failed", "Service root escapes approved apps root."
        )
    gid = _group_id(group, account.pw_gid)
    releases = service_root / "releases"
    shared = service_root / "shared"
    for path in (service_root, releases, shared):
        path.mkdir(parents=True, exist_ok=True)
    try:
        for path in (service_root, releases):
            os.chown(path, 0, 0)
            os.chmod(path, 0o755)
        os.chown(shared, account.pw_uid, gid)
        os.chmod(shared, 0o750)
    except OSError as exc:
        raise TakeoverExecutionError(
            "release_prepare_failed", "Unable to prepare release directory ownership."
        ) from exc
    return service_root


def _prepare_release_destination(
    release: Path,
    *,
    user: str,
    group: str,
) -> None:
    account = _account(user)
    gid = _group_id(group, account.pw_gid)
    try:
        release.mkdir(mode=0o750, parents=False, exist_ok=False)
        os.chown(release, account.pw_uid, gid)
        os.chmod(release, 0o750)
    except OSError as exc:
        raise TakeoverExecutionError(
            "release_prepare_failed", "Unable to allocate takeover release directory."
        ) from exc


def _seal_release(
    release: Path,
    service_root: Path,
    *,
    writable_paths: tuple[Path, ...] = (),
) -> None:
    release = release.resolve()
    releases_root = (service_root.resolve() / "releases").resolve()
    if (
        not release.is_relative_to(releases_root)
        or release == releases_root
        or not release.is_dir()
        or release.is_symlink()
    ):
        raise TakeoverExecutionError(
            "release_validation_failed", "Cannot seal an unmanaged release path."
        )

    writable_roots: tuple[Path, ...] = tuple(
        path.resolve() for path in writable_paths
    )
    for writable in writable_roots:
        if (
            not writable.is_relative_to(release)
            or writable == release
            or writable.is_symlink()
            or not writable.is_dir()
        ):
            raise TakeoverExecutionError(
                "release_validation_failed", "Invalid writable runtime path."
            )

    def is_writable_runtime_path(path: Path) -> bool:
        resolved = path.resolve(strict=False)
        return any(
            resolved == writable or resolved.is_relative_to(writable)
            for writable in writable_roots
        )

    def seal(path: Path) -> None:
        if is_writable_runtime_path(path):
            return
        try:
            if path.is_symlink():
                os.chown(path, 0, 0, follow_symlinks=False)
                return
            current_mode = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
            os.chown(path, 0, 0)
            os.chmod(path, current_mode & ~0o222)
        except OSError as exc:
            raise TakeoverExecutionError(
                "release_prepare_failed", "Unable to seal immutable takeover release."
            ) from exc

    for root, dirs, files in os.walk(release, topdown=False, followlinks=False):
        root_path = Path(root)
        for name in files:
            seal(root_path / name)
        for name in dirs:
            seal(root_path / name)
        seal(root_path)


def _prepare_next_runtime_cache(
    cwd: Path,
    *,
    user: str,
    group: str,
) -> Path:
    next_dir = cwd / ".next"
    if not next_dir.is_dir() or next_dir.is_symlink():
        raise TakeoverExecutionError(
            "release_validation_failed", "Prepared Next.js output is missing."
        )
    cache = next_dir / "cache"
    if cache.is_symlink() or (cache.exists() and not cache.is_dir()):
        raise TakeoverExecutionError(
            "release_validation_failed", "Next.js runtime cache path is invalid."
        )
    try:
        cache.mkdir(mode=0o750, exist_ok=True)
        account = _account(user)
        gid = _group_id(group, account.pw_gid)
        os.chown(cache, account.pw_uid, gid)
        os.chmod(cache, 0o750)
    except OSError as exc:
        raise TakeoverExecutionError(
            "release_prepare_failed", "Unable to prepare writable Next.js runtime cache."
        ) from exc
    return cache


def _validate_prepare_payload(payload: dict) -> None:
    if set(payload) != _PREPARE_KEYS:
        raise TakeoverExecutionError("invalid_payload", "Invalid takeover prepare payload.")
    for field in ("takeover_id", "service_id"):
        try:
            uuid.UUID(str(payload[field]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise TakeoverExecutionError("invalid_payload", f"Invalid {field}.") from exc
    if not SLUG.fullmatch(str(payload["project_slug"])) or not SLUG.fullmatch(
        str(payload["service_name"])
    ):
        raise TakeoverExecutionError("invalid_payload", "Invalid takeover identity.")
    if not COMMIT.fullmatch(str(payload["exact_commit"])):
        raise TakeoverExecutionError(
            "invalid_exact_commit", "Takeover requires an exact lowercase commit."
        )
    if payload.get("runtime") != "node-nextjs":
        raise TakeoverExecutionError(
            "unsupported_takeover_runtime", "Stage B3 supports node-nextjs only."
        )
    root_directory = payload.get("root_directory")
    if not isinstance(root_directory, str) or not SAFE_ROOT.fullmatch(root_directory):
        raise TakeoverExecutionError(
            "release_validation_failed", "Invalid release root directory."
        )


def _validate_node_artifacts(cwd: Path, install_configuration: dict) -> None:
    package_json = cwd / "package.json"
    raw_lockfile = install_configuration.get("lockfile", "package-lock.json")
    lockfile = "package-lock.json" if raw_lockfile is True else raw_lockfile
    if not isinstance(lockfile, str) or lockfile != "package-lock.json":
        raise TakeoverExecutionError(
            "release_validation_failed", "Stage B3 requires package-lock.json."
        )
    required = (package_json, cwd / lockfile, cwd / ".next")
    if not package_json.is_file() or not (cwd / lockfile).is_file() or not (cwd / ".next").is_dir():
        raise TakeoverExecutionError(
            "release_validation_failed", "Prepared Next.js release is incomplete."
        )


def prepare_service_takeover(
    payload: dict,
    *,
    apps_root: Path = Path("/srv/digitalafarin/apps"),
) -> dict:
    _validate_prepare_payload(payload)
    try:
        source_snapshot = inspect_service(payload["unit_name"])
    except Exception as exc:
        if isinstance(exc, TakeoverExecutionError):
            raise
        raise TakeoverExecutionError(
            "release_prepare_failed", "Unable to inspect source service."
        ) from exc
    if source_snapshot.get("unit_name") != payload["unit_name"]:
        raise TakeoverExecutionError(
            "release_validation_failed", "Inspected source unit does not match takeover."
        )
    source_user = source_snapshot.get("user", "")
    account = _account(source_user)
    dropin = _managed_dropin_path(payload["unit_name"])
    if dropin.exists() or dropin.is_symlink():
        raise TakeoverExecutionError(
            "managed_dropin_conflict", "Reserved managed systemd drop-in already exists."
        )

    service_root = _ensure_release_directories(
        apps_root,
        payload["project_slug"],
        payload["service_name"],
        user=source_user,
        group=source_snapshot.get("group", ""),
    )
    try:
        release = prepare_release(
            payload["project_slug"],
            payload["service_name"],
            payload["repository"],
            payload["exact_commit"],
            apps_root=apps_root,
            run_command=lambda argv, timeout=300: run_as_user(
                source_user, argv, timeout=timeout
            ),
            prepare_destination=lambda path: _prepare_release_destination(
                path,
                user=source_user,
                group=source_snapshot.get("group", ""),
            ),
        )
    except (ReleaseError, TakeoverExecutionError) as exc:
        if isinstance(exc, TakeoverExecutionError):
            raise
        raise TakeoverExecutionError("release_prepare_failed", str(exc)) from exc

    root_directory = payload["root_directory"]
    cwd = (release / root_directory).resolve()
    if not cwd.is_relative_to(release.resolve()):
        raise TakeoverExecutionError(
            "release_validation_failed", "Root directory escapes prepared release."
        )
    executor = SystemdExecutor()
    try:
        commands = executor.recipe_commands(
            payload["runtime"],
            payload.get("install_configuration", {}),
            payload.get("build_configuration", {}),
            root_directory,
        )
    except RecipeError as exc:
        raise TakeoverExecutionError("release_validation_failed", str(exc)) from exc
    run_recipe_as_user(source_user, commands, cwd)
    _validate_node_artifacts(cwd, payload.get("install_configuration", {}))
    runtime_cache = _prepare_next_runtime_cache(
        cwd,
        user=source_user,
        group=source_snapshot.get("group", ""),
    )
    _seal_release(
        release,
        service_root,
        writable_paths=(runtime_cache,),
    )

    # account is intentionally resolved before clone/build. Keep the access here
    # so tests can prove the non-root identity path was exercised.
    _ = account
    return {
        "takeover_id": payload["takeover_id"],
        "final_state": "prepared",
        "resolved_commit": payload["exact_commit"],
        "source_snapshot": source_snapshot,
        "source_fingerprint": fingerprint_snapshot(source_snapshot),
        "release_name": release.name,
        "release_path": str(release),
        "events": [
            {"state": "inspecting", "message": ""},
            {"state": "preparing", "message": ""},
            {"state": "prepared", "message": ""},
        ],
    }



def _validate_activate_payload(payload: dict) -> None:
    if set(payload) != _ACTIVATE_KEYS:
        raise TakeoverExecutionError("invalid_payload", "Invalid takeover activation payload.")
    for field in ("takeover_id", "service_id"):
        try:
            uuid.UUID(str(payload[field]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise TakeoverExecutionError("invalid_payload", f"Invalid {field}.") from exc
    if not SLUG.fullmatch(str(payload["project_slug"])) or not SLUG.fullmatch(
        str(payload["service_name"])
    ):
        raise TakeoverExecutionError("invalid_payload", "Invalid takeover identity.")
    if not COMMIT.fullmatch(str(payload["exact_commit"])):
        raise TakeoverExecutionError("invalid_exact_commit", "Invalid exact commit.")
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload["source_fingerprint"])):
        raise TakeoverExecutionError("invalid_payload", "Invalid source fingerprint.")
    if not re.fullmatch(
        r"[0-9]{8}-[0-9]{6}-[0-9a-f]{7}(?:-[0-9]+)?",
        str(payload["release_name"]),
    ):
        raise TakeoverExecutionError("release_validation_failed", "Invalid release name.")
    root_directory = payload.get("root_directory")
    if not isinstance(root_directory, str) or not SAFE_ROOT.fullmatch(root_directory):
        raise TakeoverExecutionError("release_validation_failed", "Invalid release root directory.")


def _activation_paths(payload: dict, apps_root: Path) -> tuple[Path, Path, Path]:
    root = apps_root.resolve()
    service_root = (root / payload["project_slug"] / payload["service_name"]).resolve()
    if not service_root.is_relative_to(root):
        raise TakeoverExecutionError("takeover_activation_failed", "Service root escapes apps root.")
    release = (service_root / "releases" / payload["release_name"]).resolve()
    releases_root = (service_root / "releases").resolve()
    if not release.is_relative_to(releases_root) or not release.is_dir():
        raise TakeoverExecutionError("release_validation_failed", "Prepared release is missing.")
    expected = str(release)
    if payload.get("release_path") != expected:
        raise TakeoverExecutionError("release_validation_failed", "Prepared release path mismatch.")
    cwd = (release / payload["root_directory"]).resolve()
    if not cwd.is_relative_to(release) or not (cwd / ".next").is_dir():
        raise TakeoverExecutionError("release_validation_failed", "Prepared Next.js artifacts are missing.")
    return service_root, release, cwd


def _validate_previous_current(service_root: Path) -> Path | None:
    current = service_root / "current"
    if not current.exists() and not current.is_symlink():
        return None
    if not current.is_symlink():
        raise TakeoverExecutionError(
            "takeover_activation_failed", "Current path is not a managed symlink."
        )
    target = current.resolve(strict=False)
    releases_root = (service_root / "releases").resolve()
    if not target.is_relative_to(releases_root) or not target.is_dir():
        raise TakeoverExecutionError(
            "takeover_activation_failed", "Current symlink points outside managed releases."
        )
    return target


def _restore_current(service_root: Path, previous: Path | None) -> None:
    current = service_root / "current"
    if previous is None:
        if current.is_symlink():
            current.unlink()
        elif current.exists():
            raise TakeoverExecutionError(
                "takeover_rollback_failed", "Current path cannot be restored safely."
            )
        return
    atomic_activate(service_root, previous)


def _cleanup_failed_release(release: Path) -> None:
    import shutil

    if release.is_dir() and not release.is_symlink():
        shutil.rmtree(release)


def activate_service_takeover(
    payload: dict,
    *,
    apps_root: Path = Path("/srv/digitalafarin/apps"),
) -> dict:
    _validate_activate_payload(payload)
    service_root, release, cwd = _activation_paths(payload, apps_root)
    try:
        snapshot_now = inspect_service(payload["unit_name"])
    except Exception as exc:
        raise TakeoverExecutionError(
            "takeover_activation_failed", "Unable to re-inspect source service."
        ) from exc
    if fingerprint_snapshot(snapshot_now) != payload["source_fingerprint"]:
        raise TakeoverExecutionError(
            "service_configuration_changed",
            "Source service configuration changed after prepare.",
        )

    previous = _validate_previous_current(service_root)
    dropin = _managed_dropin_path(payload["unit_name"])
    if dropin.exists() or dropin.is_symlink():
        raise TakeoverExecutionError(
            "managed_dropin_conflict", "Reserved managed systemd drop-in already exists."
        )

    mutated = False
    installed_dropin: Path | None = None
    try:
        actual_previous = atomic_activate(service_root, release)
        if actual_previous != previous:
            raise TakeoverExecutionError(
                "takeover_activation_failed", "Current release changed during activation."
            )
        mutated = True
        managed_working_directory = (
            service_root / "current" / payload["root_directory"]
        )
        installed_dropin = _write_managed_dropin(
            payload["unit_name"], managed_working_directory
        )
        daemon_reload()
        restart_takeover_unit(payload["unit_name"])
        check_http_health_stable(payload["health_check"])
    except (HealthCheckError, TakeoverExecutionError, OSError, ReleaseError, Exception) as exc:
        if not mutated:
            if isinstance(exc, TakeoverExecutionError):
                raise
            raise TakeoverExecutionError("takeover_activation_failed", type(exc).__name__) from exc
        try:
            _restore_current(service_root, previous)
            if installed_dropin is not None or dropin.exists() or dropin.is_symlink():
                _remove_managed_dropin(payload["unit_name"])
            daemon_reload()
            restart_takeover_unit(payload["unit_name"])
            check_http_health_stable(payload["health_check"])
        except Exception as rollback_exc:
            raise TakeoverExecutionError(
                "takeover_rollback_failed",
                "Controlled takeover rollback did not restore healthy service.",
            ) from rollback_exc
        _cleanup_failed_release(release)
        return {
            "takeover_id": payload["takeover_id"],
            "final_state": "rolled_back",
            "resolved_commit": payload["exact_commit"],
            "release_name": payload["release_name"],
            "previous_current_path": str(previous) if previous else None,
            "managed_dropin_path": str(dropin),
            "events": [
                {"state": "activating", "message": ""},
                {"state": "verifying", "message": ""},
                {
                    "state": "rolled_back",
                    "message": "New release failed health verification; original service restored.",
                },
            ],
        }

    return {
        "takeover_id": payload["takeover_id"],
        "final_state": "succeeded",
        "resolved_commit": payload["exact_commit"],
        "release_name": payload["release_name"],
        "previous_current_path": str(previous) if previous else None,
        "managed_dropin_path": str(installed_dropin or dropin),
        "events": [
            {"state": "activating", "message": ""},
            {"state": "verifying", "message": ""},
            {"state": "succeeded", "message": ""},
        ],
    }
