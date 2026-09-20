import grp
import os
import pwd
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .executors.systemd import RecipeError, SystemdExecutor
from .releases import COMMIT, SLUG, ReleaseError, atomic_activate, prepare_release
from .takeover_systemd import (
    TakeoverSystemdError,
    daemon_reload,
    fingerprint_snapshot,
    inspect_service,
    managed_dropin_path,
    remove_managed_dropin,
    restart_takeover_unit,
    write_managed_dropin,
)


APPS_ROOT = Path("/srv/digitalafarin/apps")
SYSTEMD_ROOT = Path("/etc/systemd/system")
SAFE_ROOT = re.compile(r"^(?:\.|[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)$")


def _is_safe_root_directory(value: object) -> bool:
    if not isinstance(value, str) or not SAFE_ROOT.fullmatch(value):
        return False
    if value == ".":
        return True
    return all(part not in {".", ".."} for part in value.split("/"))
RELEASE_NAME = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{7}(?:-[0-9]+)?$")
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")

_PREPARE_KEYS = {
    "project_slug",
    "unit_name",
    "service_name",
    "repository",
    "exact_commit",
    "root_directory",
    "install_configuration",
    "build_configuration",
    "user",
    "group",
}
_ACTIVATE_KEYS = {
    "project_slug",
    "service_name",
    "unit_name",
    "release_name",
    "root_directory",
    "source_fingerprint",
}
_ROLLBACK_KEYS = {
    "project_slug",
    "service_name",
    "unit_name",
    "previous_release_name",
}
_CLEANUP_KEYS = {"project_slug", "service_name", "unit_name", "release_name"}


class TakeoverHelperDomainError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def allowed_bindings_from_env() -> set[tuple[str, str, str]]:
    raw = os.environ.get("DIGITALAFARIN_TAKEOVER_ALLOWED_BINDINGS", "")
    bindings: set[tuple[str, str, str]] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        parts = tuple(part.strip() for part in item.split("|"))
        if len(parts) != 3 or not all(parts):
            raise TakeoverHelperDomainError(
                "helper_configuration_error",
                "Invalid privileged helper binding configuration.",
            )
        bindings.add(parts)
    return bindings


def _require_exact_keys(params: dict[str, Any], expected: set[str]) -> None:
    if not isinstance(params, dict) or set(params) != expected:
        raise TakeoverHelperDomainError(
            "helper_invalid_request", "Invalid privileged helper parameters."
        )


def _validate_identity(project_slug: Any, service_name: Any) -> tuple[str, str]:
    project = str(project_slug)
    service = str(service_name)
    if not SLUG.fullmatch(project) or not SLUG.fullmatch(service):
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Invalid takeover service identity."
        )
    return project, service


def _validate_root_directory(value: Any) -> str:
    if not _is_safe_root_directory(value):
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Invalid release root directory."
        )
    return value


def _validate_release_name(value: Any) -> str:
    value = str(value)
    if not RELEASE_NAME.fullmatch(value):
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Invalid release name."
        )
    return value


def _validate_repository(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Invalid repository URL."
        )
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.query
    ):
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Takeover repository must be a credential-free HTTPS URL."
        )
    return value


def _validate_binding(
    project_slug: str,
    service_name: str,
    unit_name: Any,
    allowed_bindings: set[tuple[str, str, str]],
) -> str:
    unit = str(unit_name)
    if not allowed_bindings or (project_slug, service_name, unit) not in allowed_bindings:
        raise TakeoverHelperDomainError(
            "helper_identity_not_allowed",
            "Takeover project/service/unit binding is not allowlisted.",
        )
    return unit


def _account(user: Any):
    if not isinstance(user, str) or not user or user == "root":
        raise TakeoverHelperDomainError(
            "source_user_unsafe", "Takeover build requires a non-root service user."
        )
    try:
        return pwd.getpwnam(user)
    except KeyError as exc:
        raise TakeoverHelperDomainError(
            "source_user_unsafe", "Source service user does not exist."
        ) from exc


def _group_id(group: Any, fallback_gid: int) -> int:
    if not isinstance(group, str) or not group:
        return fallback_gid
    try:
        return grp.getgrnam(group).gr_gid
    except KeyError:
        return fallback_gid


def _service_root(apps_root: Path, project_slug: str, service_name: str) -> Path:
    root = apps_root.resolve()
    service_root = (root / project_slug / service_name).resolve()
    if not service_root.is_relative_to(root) or service_root == root:
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Service root escapes approved apps root."
        )
    return service_root


def _release_path(service_root: Path, release_name: str) -> Path:
    releases_root = (service_root / "releases").resolve()
    release = (releases_root / release_name).resolve()
    if not release.is_relative_to(releases_root) or release == releases_root:
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Release path escapes managed releases root."
        )
    return release


def _run_as_user(
    user: str,
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 900,
) -> None:
    _account(user)
    if not argv or not all(isinstance(item, str) and item for item in argv):
        raise TakeoverHelperDomainError(
            "release_prepare_failed", "Invalid takeover build command."
        )
    try:
        result = subprocess.run(
            [
                "runuser",
                "-u",
                user,
                "--",
                "env",
                "-i",
                "HOME=/tmp",
                "NPM_CONFIG_CACHE=/tmp/.npm-digitalafarin-takeover",
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
        raise TakeoverHelperDomainError(
            "release_prepare_failed", type(exc).__name__
        ) from exc
    if result.returncode != 0:
        raise TakeoverHelperDomainError(
            "release_prepare_failed", "Takeover build command failed."
        )


def _ensure_release_directories(
    apps_root: Path,
    project_slug: str,
    service_name: str,
    *,
    user: str,
    group: str,
) -> Path:
    account = _account(user)
    service_root = _service_root(apps_root, project_slug, service_name)
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
        raise TakeoverHelperDomainError(
            "release_prepare_failed", "Unable to prepare release directory ownership."
        ) from exc
    return service_root


def _prepare_release_destination(release: Path, *, user: str, group: str) -> None:
    account = _account(user)
    gid = _group_id(group, account.pw_gid)
    try:
        release.mkdir(mode=0o750, parents=False, exist_ok=False)
        os.chown(release, account.pw_uid, gid)
        os.chmod(release, 0o750)
    except OSError as exc:
        raise TakeoverHelperDomainError(
            "release_prepare_failed", "Unable to allocate takeover release directory."
        ) from exc


def _validate_node_artifacts(cwd: Path, install_configuration: dict[str, Any]) -> None:
    raw_lockfile = install_configuration.get("lockfile", "package-lock.json")
    lockfile = "package-lock.json" if raw_lockfile is True else raw_lockfile
    if lockfile != "package-lock.json":
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Takeover requires package-lock.json."
        )
    if (
        not (cwd / "package.json").is_file()
        or not (cwd / "package-lock.json").is_file()
        or not (cwd / ".next").is_dir()
    ):
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Prepared Next.js release is incomplete."
        )


def _prepare_next_runtime_cache(cwd: Path, *, user: str, group: str) -> Path:
    next_dir = cwd / ".next"
    if not next_dir.is_dir() or next_dir.is_symlink():
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Prepared Next.js output is missing."
        )
    cache = next_dir / "cache"
    if cache.is_symlink() or (cache.exists() and not cache.is_dir()):
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Next.js runtime cache path is invalid."
        )
    account = _account(user)
    gid = _group_id(group, account.pw_gid)
    try:
        cache.mkdir(mode=0o750, exist_ok=True)
        os.chown(cache, account.pw_uid, gid)
        os.chmod(cache, 0o750)
    except OSError as exc:
        raise TakeoverHelperDomainError(
            "release_prepare_failed", "Unable to prepare writable Next.js runtime cache."
        ) from exc
    return cache


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
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Cannot seal an unmanaged release path."
        )

    writable_roots = tuple(path.resolve() for path in writable_paths)
    for writable in writable_roots:
        if (
            not writable.is_relative_to(release)
            or writable == release
            or writable.is_symlink()
            or not writable.is_dir()
        ):
            raise TakeoverHelperDomainError(
                "release_validation_failed", "Invalid writable runtime path."
            )

    def writable(path: Path) -> bool:
        resolved = path.resolve(strict=False)
        return any(
            resolved == candidate or resolved.is_relative_to(candidate)
            for candidate in writable_roots
        )

    def seal(path: Path) -> None:
        if writable(path):
            return
        try:
            if path.is_symlink():
                os.chown(path, 0, 0, follow_symlinks=False)
                return
            current_mode = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
            os.chown(path, 0, 0)
            os.chmod(path, current_mode & ~0o222)
        except OSError as exc:
            raise TakeoverHelperDomainError(
                "release_prepare_failed", "Unable to seal immutable takeover release."
            ) from exc

    for root, dirs, files in os.walk(release, topdown=False, followlinks=False):
        root_path = Path(root)
        for name in files:
            seal(root_path / name)
        for name in dirs:
            seal(root_path / name)
        seal(root_path)


def prepare_node_nextjs_release(
    params: dict[str, Any],
    *,
    allowed_bindings: set[tuple[str, str, str]] | None = None,
    apps_root: Path = APPS_ROOT,
) -> dict[str, Any]:
    _require_exact_keys(params, _PREPARE_KEYS)
    project_slug, service_name = _validate_identity(
        params["project_slug"], params["service_name"]
    )
    allowed = (
        allowed_bindings if allowed_bindings is not None else allowed_bindings_from_env()
    )
    unit_name = _validate_binding(project_slug, service_name, params["unit_name"], allowed)
    repository = _validate_repository(params["repository"])
    exact_commit = str(params["exact_commit"])
    if not COMMIT.fullmatch(exact_commit):
        raise TakeoverHelperDomainError(
            "invalid_exact_commit", "Takeover requires an exact lowercase commit."
        )
    root_directory = _validate_root_directory(params["root_directory"])
    install_configuration = params["install_configuration"]
    build_configuration = params["build_configuration"]
    if not isinstance(install_configuration, dict) or not isinstance(
        build_configuration, dict
    ):
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Invalid build configuration."
        )
    user = params["user"]
    group = params["group"]
    _account(user)
    try:
        source_snapshot = inspect_service(unit_name)
    except (TakeoverSystemdError, OSError) as exc:
        raise TakeoverHelperDomainError(
            "release_prepare_failed", "Unable to inspect source service identity."
        ) from exc
    if source_snapshot.get("user") != user or source_snapshot.get("group", "") != group:
        raise TakeoverHelperDomainError(
            "service_configuration_changed",
            "Source service user/group changed before privileged prepare.",
        )
    service_root = _ensure_release_directories(
        apps_root,
        project_slug,
        service_name,
        user=user,
        group=group,
    )
    allocated: list[Path] = []

    def allocate(path: Path) -> None:
        _prepare_release_destination(path, user=user, group=group)
        allocated.append(path)

    try:
        try:
            release = prepare_release(
                project_slug,
                service_name,
                repository,
                exact_commit,
                apps_root=apps_root,
                run_command=lambda argv, timeout=300: _run_as_user(
                    user, argv, timeout=timeout
                ),
                prepare_destination=allocate,
            )
        except TakeoverHelperDomainError:
            raise
        except ReleaseError as exc:
            raise TakeoverHelperDomainError("release_prepare_failed", str(exc)) from exc

        cwd = (release / root_directory).resolve()
        if not cwd.is_relative_to(release.resolve()):
            raise TakeoverHelperDomainError(
                "release_validation_failed", "Root directory escapes prepared release."
            )
        executor = SystemdExecutor()
        try:
            commands = executor.recipe_commands(
                "node-nextjs",
                install_configuration,
                build_configuration,
                root_directory,
            )
        except RecipeError as exc:
            raise TakeoverHelperDomainError("release_validation_failed", str(exc)) from exc
        for command in commands:
            _run_as_user(user, command, cwd=cwd, timeout=900)
        _validate_node_artifacts(cwd, install_configuration)
        runtime_cache = _prepare_next_runtime_cache(cwd, user=user, group=group)
        _seal_release(release, service_root, writable_paths=(runtime_cache,))
        allocated.clear()
        return {"release_name": release.name, "release_path": str(release)}
    except Exception:
        for candidate in allocated:
            try:
                resolved = candidate.resolve(strict=False)
                releases_root = (service_root / "releases").resolve()
                if (
                    resolved.is_relative_to(releases_root)
                    and resolved != releases_root
                    and candidate.is_dir()
                    and not candidate.is_symlink()
                ):
                    shutil.rmtree(candidate)
            except OSError:
                pass
        raise


def _validate_previous_current(service_root: Path) -> Path | None:
    current = service_root / "current"
    if not current.exists() and not current.is_symlink():
        return None
    if not current.is_symlink():
        raise TakeoverHelperDomainError(
            "takeover_activation_failed", "Current path is not a managed symlink."
        )
    target = current.resolve(strict=False)
    releases_root = (service_root / "releases").resolve()
    if not target.is_relative_to(releases_root) or not target.is_dir():
        raise TakeoverHelperDomainError(
            "takeover_activation_failed", "Current symlink points outside managed releases."
        )
    return target


def _restore_current(service_root: Path, previous: Path | None) -> None:
    current = service_root / "current"
    if previous is None:
        if current.is_symlink():
            current.unlink()
        elif current.exists():
            raise TakeoverHelperDomainError(
                "takeover_rollback_failed", "Current path cannot be restored safely."
            )
        return
    try:
        atomic_activate(service_root, previous)
    except ReleaseError as exc:
        raise TakeoverHelperDomainError(
            "takeover_rollback_failed", "Unable to restore previous release."
        ) from exc


def activate_release(
    params: dict[str, Any],
    *,
    allowed_bindings: set[tuple[str, str, str]] | None = None,
    apps_root: Path = APPS_ROOT,
    systemd_root: Path = SYSTEMD_ROOT,
) -> dict[str, Any]:
    _require_exact_keys(params, _ACTIVATE_KEYS)
    project_slug, service_name = _validate_identity(
        params["project_slug"], params["service_name"]
    )
    allowed = (
        allowed_bindings if allowed_bindings is not None else allowed_bindings_from_env()
    )
    unit_name = _validate_binding(project_slug, service_name, params["unit_name"], allowed)
    release_name = _validate_release_name(params["release_name"])
    root_directory = _validate_root_directory(params["root_directory"])
    expected_fingerprint = str(params["source_fingerprint"])
    if not FINGERPRINT.fullmatch(expected_fingerprint):
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Invalid source fingerprint."
        )

    try:
        snapshot = inspect_service(unit_name)
        actual_fingerprint = fingerprint_snapshot(snapshot)
    except (TakeoverSystemdError, OSError) as exc:
        raise TakeoverHelperDomainError(
            "takeover_activation_failed", "Unable to re-inspect source service."
        ) from exc
    if actual_fingerprint != expected_fingerprint:
        raise TakeoverHelperDomainError(
            "service_configuration_changed",
            "Source service configuration changed after prepare.",
        )

    service_root = _service_root(apps_root, project_slug, service_name)
    release = _release_path(service_root, release_name)
    cwd = (release / root_directory).resolve()
    if (
        not release.is_dir()
        or release.is_symlink()
        or not cwd.is_relative_to(release)
        or not (cwd / ".next").is_dir()
    ):
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Prepared Next.js artifacts are missing."
        )
    previous = _validate_previous_current(service_root)
    dropin = managed_dropin_path(unit_name, systemd_root=systemd_root)
    if dropin.exists() or dropin.is_symlink():
        raise TakeoverHelperDomainError(
            "managed_dropin_conflict", "Reserved managed systemd drop-in already exists."
        )

    mutated = False
    dropin_installed = False
    try:
        actual_previous = atomic_activate(service_root, release)
        mutated = True
        if actual_previous != previous:
            raise TakeoverHelperDomainError(
                "takeover_activation_failed", "Current release changed during activation."
            )
        managed_working_directory = service_root / "current" / root_directory
        write_managed_dropin(
            unit_name,
            managed_working_directory,
            systemd_root=systemd_root,
            apps_root=apps_root,
        )
        dropin_installed = True
        daemon_reload()
        restart_takeover_unit(unit_name)
    except Exception as exc:
        if not mutated:
            if isinstance(exc, TakeoverHelperDomainError):
                raise
            raise TakeoverHelperDomainError(
                "takeover_activation_failed", "Privileged activation failed."
            ) from exc
        try:
            _restore_current(service_root, previous)
            if dropin_installed or dropin.exists() or dropin.is_symlink():
                remove_managed_dropin(unit_name, systemd_root=systemd_root)
            daemon_reload()
            restart_takeover_unit(unit_name)
        except Exception as rollback_exc:
            raise TakeoverHelperDomainError(
                "takeover_rollback_failed",
                "Privileged activation rollback failed.",
            ) from rollback_exc
        if isinstance(exc, TakeoverHelperDomainError):
            raise exc
        raise TakeoverHelperDomainError(
            "takeover_activation_failed", "Privileged activation failed and was rolled back."
        ) from exc

    return {
        "previous_release_name": previous.name if previous else None,
        "previous_current_path": str(previous) if previous else None,
        "managed_dropin_path": str(dropin),
    }


def rollback_activation(
    params: dict[str, Any],
    *,
    allowed_bindings: set[tuple[str, str, str]] | None = None,
    apps_root: Path = APPS_ROOT,
    systemd_root: Path = SYSTEMD_ROOT,
) -> dict[str, Any]:
    _require_exact_keys(params, _ROLLBACK_KEYS)
    project_slug, service_name = _validate_identity(
        params["project_slug"], params["service_name"]
    )
    allowed = (
        allowed_bindings if allowed_bindings is not None else allowed_bindings_from_env()
    )
    unit_name = _validate_binding(project_slug, service_name, params["unit_name"], allowed)
    previous_name = params["previous_release_name"]
    if previous_name is not None:
        previous_name = _validate_release_name(previous_name)

    service_root = _service_root(apps_root, project_slug, service_name)
    previous = (
        _release_path(service_root, previous_name) if previous_name is not None else None
    )
    if previous is not None and not previous.is_dir():
        raise TakeoverHelperDomainError(
            "takeover_rollback_failed", "Previous release is missing."
        )
    try:
        _restore_current(service_root, previous)
        dropin = managed_dropin_path(unit_name, systemd_root=systemd_root)
        if dropin.exists() or dropin.is_symlink():
            remove_managed_dropin(unit_name, systemd_root=systemd_root)
        daemon_reload()
        restart_takeover_unit(unit_name)
    except TakeoverHelperDomainError:
        raise
    except Exception as exc:
        raise TakeoverHelperDomainError(
            "takeover_rollback_failed", "Privileged takeover rollback failed."
        ) from exc
    return {
        "previous_release_name": previous_name,
        "previous_current_path": str(previous) if previous else None,
    }


def cleanup_release(
    params: dict[str, Any],
    *,
    allowed_bindings: set[tuple[str, str, str]] | None = None,
    apps_root: Path = APPS_ROOT,
) -> dict[str, Any]:
    _require_exact_keys(params, _CLEANUP_KEYS)
    project_slug, service_name = _validate_identity(
        params["project_slug"], params["service_name"]
    )
    allowed = (
        allowed_bindings if allowed_bindings is not None else allowed_bindings_from_env()
    )
    _validate_binding(project_slug, service_name, params["unit_name"], allowed)
    release_name = _validate_release_name(params["release_name"])
    service_root = _service_root(apps_root, project_slug, service_name)
    release = _release_path(service_root, release_name)
    current = service_root / "current"
    if current.is_symlink() and current.resolve(strict=False) == release:
        raise TakeoverHelperDomainError(
            "takeover_cleanup_failed", "Refusing to delete the active release."
        )
    if release.exists():
        if release.is_symlink() or not release.is_dir():
            raise TakeoverHelperDomainError(
                "takeover_cleanup_failed", "Release cleanup target is unsafe."
            )
        try:
            shutil.rmtree(release)
        except OSError as exc:
            raise TakeoverHelperDomainError(
                "takeover_cleanup_failed", "Unable to remove failed release."
            ) from exc
    return {"removed": not release.exists()}


def dispatch_helper_operation(
    operation: str,
    params: dict[str, Any],
    *,
    allowed_bindings: set[tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    if operation == "prepare_node_nextjs_release":
        return prepare_node_nextjs_release(params, allowed_bindings=allowed_bindings)
    if operation == "activate_release":
        return activate_release(params, allowed_bindings=allowed_bindings)
    if operation == "rollback_activation":
        return rollback_activation(params, allowed_bindings=allowed_bindings)
    if operation == "cleanup_release":
        return cleanup_release(params, allowed_bindings=allowed_bindings)
    raise TakeoverHelperDomainError(
        "helper_operation_not_allowed", "Privileged helper operation is not allowlisted."
    )
