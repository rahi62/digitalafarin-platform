import grp
import os
import pwd
import re
import shutil
import stat
from datetime import datetime, timezone
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
from .takeover_worker import TakeoverWorkerError, run_takeover_worker
from .source_providers import LocalSourceProvider, SourceProviderError, SourceRequest


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
    "exact_commit",
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


def trusted_source_repositories_from_env() -> dict[tuple[str, str, str], Path]:
    raw = os.environ.get("DIGITALAFARIN_TAKEOVER_SOURCE_REPOSITORIES", "")
    repositories: dict[tuple[str, str, str], Path] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split("|")]
        if len(parts) != 4 or not all(parts):
            raise TakeoverHelperDomainError(
                "helper_configuration_error",
                "Invalid privileged helper source repository configuration.",
            )
        project_slug, service_name, unit_name, raw_path = parts
        source = Path(raw_path)
        if not source.is_absolute() or ".." in source.parts:
            raise TakeoverHelperDomainError(
                "helper_configuration_error",
                "Trusted takeover source repository path must be absolute.",
            )
        repositories[(project_slug, service_name, unit_name)] = source
    return repositories


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
    if service_root != root / project_slug / service_name:
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Service root escapes approved apps root."
        )
    return service_root


def _release_path(service_root: Path, release_name: str) -> Path:
    releases_path = service_root / "releases"
    candidate = releases_path / release_name
    if releases_path.is_symlink() or candidate.is_symlink():
        raise TakeoverHelperDomainError("release_validation_failed", "Aliased release path.")
    releases_root = releases_path.resolve()
    release = candidate.resolve()
    if not release.is_relative_to(releases_root) or release == releases_root:
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Release path escapes managed releases root."
        )
    return release


def _trusted_local_source_repository(
    project_slug: str,
    service_name: str,
    unit_name: str,
    exact_commit: str,
    expected_repository: str,
    user: str,
    group: str,
    source_repositories: dict[tuple[str, str, str], Path],
) -> Path:
    configured = source_repositories.get((project_slug, service_name, unit_name))
    if configured is None:
        raise TakeoverHelperDomainError(
            "helper_configuration_error",
            "No trusted local source repository is configured for this takeover binding.",
        )
    if configured.is_symlink():
        raise TakeoverHelperDomainError(
            "helper_configuration_error",
            "Trusted local source repository cannot be a symlink.",
        )
    try:
        source = configured.resolve(strict=True)
    except OSError as exc:
        raise TakeoverHelperDomainError(
            "helper_configuration_error",
            "Trusted local source repository is unavailable.",
        ) from exc
    if not source.is_dir():
        raise TakeoverHelperDomainError(
            "helper_configuration_error",
            "Trusted local source repository is not a directory.",
        )
    try:
        remote = run_takeover_worker(
            phase="source_verify",
            user=user,
            group=group,
            argv=["git", "-C", str(source), "remote", "get-url", "origin"],
            timeout=30,
        )
        if _validate_repository(remote) != _validate_repository(
            expected_repository
        ):
            raise TakeoverHelperDomainError(
                "managed_repository_not_allowed",
                "Trusted local source origin does not match the managed repository.",
            )
        run_takeover_worker(
            phase="source_sync",
            user=user,
            group=group,
            argv=["git", "-C", str(source), "fetch", "--no-tags", "origin", exact_commit],
            timeout=120,
        )
        run_takeover_worker(
            phase="source_sync",
            user=user,
            group=group,
            argv=["git", "-C", str(source), "checkout", "--detach", exact_commit],
            timeout=30,
        )
        head = run_takeover_worker(
            phase="source_verify",
            user=user,
            group=group,
            argv=["git", "-C", str(source), "rev-parse", "HEAD"],
            timeout=30,
        )
    except TakeoverHelperDomainError:
        raise
    except TakeoverWorkerError as exc:
        raise TakeoverHelperDomainError(
            "source_sync_failed", "Unable to sync trusted source to the requested commit."
        ) from exc
    if not COMMIT.fullmatch(head) or head != exact_commit:
        raise TakeoverHelperDomainError(
            "source_sync_failed",
            "Trusted local source HEAD does not match the requested production commit after sync.",
        )
    return source


def _artifact_source(source_id: Any) -> Path:
    value = str(source_id or "")
    if not re.fullmatch(r"[0-9a-f-]{36}", value):
        raise TakeoverHelperDomainError("source_artifact_invalid", "Invalid source artifact identity.")
    path = Path("/var/lib/digitalafarin-agent/sources") / f"{value}.bundle"
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise TakeoverHelperDomainError("source_artifact_missing", "Source artifact is unavailable.") from exc
    expected_parent = Path("/var/lib/digitalafarin-agent/sources").resolve(strict=True)
    if resolved.parent != expected_parent or resolved.is_symlink() or not resolved.is_file():
        raise TakeoverHelperDomainError("source_artifact_invalid", "Invalid source artifact path.")
    return resolved


def _run_as_worker(
    user: str,
    group: str,
    argv: list[str],
    *,
    cwd: Path | None = None,
    writable_path: Path | None = None,
    phase: str,
    npm_cache: bool = False,
    timeout: int = 900,
) -> None:
    try:
        run_takeover_worker(
            phase=phase,
            user=user,
            group=group,
            argv=argv,
            cwd=cwd,
            writable_path=writable_path,
            npm_cache=npm_cache,
            timeout=timeout,
        )
    except TakeoverWorkerError as exc:
        raise TakeoverHelperDomainError(
            "release_prepare_failed", "Takeover build command failed."
        ) from exc


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
        # Workers need traversal, but never list or write access, through the managed path.
        if apps_root == APPS_ROOT:
            os.chmod(apps_root.parent, 0o751)
        os.chmod(apps_root, 0o751)
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


def _prepare_release_destination(
    release: Path,
    *,
    service_root: Path,
    user: str,
    group: str,
) -> None:
    account = _account(user)
    gid = _group_id(group, account.pw_gid)
    releases_root = (service_root / "releases").resolve(strict=True)
    if (
        release.is_symlink()
        or release.parent.resolve(strict=True) != releases_root
        or not RELEASE_NAME.fullmatch(release.name)
        or release.exists()
    ):
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Invalid takeover release destination."
        )
    created = False
    try:
        release.mkdir(mode=0o750, parents=False, exist_ok=False)
        created = True
        if release.is_symlink() or release.resolve(strict=True).parent != releases_root:
            raise OSError("release destination changed during allocation")
        if any(release.iterdir()):
            raise OSError("release destination is not empty")
        os.chown(release, account.pw_uid, gid)
        os.chmod(release, 0o750)
    except OSError as exc:
        if created:
            try:
                release.rmdir()
            except OSError:
                pass
        raise TakeoverHelperDomainError(
            "release_prepare_failed", "Unable to allocate takeover release directory."
        ) from exc


def _allocate_takeover_release(
    service_root: Path,
    exact_commit: str,
    *,
    user: str,
    group: str,
    timestamp: str | None = None,
) -> Path:
    if not COMMIT.fullmatch(exact_commit):
        raise TakeoverHelperDomainError(
            "invalid_exact_commit", "Takeover requires an exact lowercase commit."
        )
    releases_path = service_root / "releases"
    if releases_path.is_symlink():
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Invalid managed releases root."
        )
    releases_root = releases_path.resolve(strict=True)
    if not releases_root.is_dir():
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Invalid managed releases root."
        )
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base_name = f"{stamp}-{exact_commit[:7]}"
    sequence = 1
    while True:
        name = base_name if sequence == 1 else f"{base_name}-{sequence}"
        release = releases_root / name
        if not release.exists() and not release.is_symlink():
            _prepare_release_destination(
                release,
                service_root=service_root,
                user=user,
                group=group,
            )
            return release
        sequence += 1


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
    runtime_gid: int,
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

    # Keep the immutable release root executable by the service runtime group.
    # The unprivileged Agent is intentionally not a member of that group.
    try:
        os.chown(release, 0, runtime_gid)
        os.chmod(release, 0o550)
    except OSError as exc:
        raise TakeoverHelperDomainError(
            "release_prepare_failed",
            "Unable to grant runtime traversal on sealed takeover release.",
        ) from exc


def _validate_prepared_release(
    release: Path,
    service_root: Path,
    root_directory: str,
    exact_commit: str,
    install_configuration: dict[str, Any],
    *,
    sealed: bool,
) -> str:
    """Validate built content as Helper, including the existing sealing policy."""
    try:
        releases_root = service_root / "releases"
        if (
            releases_root.resolve(strict=True) != releases_root
            or release.parent != releases_root
            or release.resolve(strict=True) != release
            or not release.is_dir()
            or not RELEASE_NAME.fullmatch(release.name)
            or not COMMIT.fullmatch(exact_commit)
            or release.name.split("-")[2] != exact_commit[:7]
        ):
            raise ValueError("invalid release path or commit")
        cwd = release / root_directory
        if cwd.resolve(strict=True) != cwd or not cwd.is_dir():
            raise ValueError("invalid release root directory")
        _validate_node_artifacts(cwd, install_configuration)
        for path in (cwd / "package.json", cwd / "package-lock.json", cwd / ".next", release / ".git/HEAD"):
            if path.resolve(strict=True) != path:
                raise ValueError("aliased release artifact")
        # prepare_release performs a detached checkout. Read HEAD as data, never
        # execute repository-controlled Git configuration as the privileged user.
        head = release / ".git/HEAD"
        head_info = head.lstat()
        if not stat.S_ISREG(head_info.st_mode) or head_info.st_size not in {40, 41}:
            raise ValueError("invalid detached HEAD file")
        with head.open(encoding="ascii") as stream:
            resolved_commit = stream.read(42).strip()
        if not COMMIT.fullmatch(resolved_commit) or resolved_commit != exact_commit:
            raise ValueError("prepared commit mismatch")

        cache = cwd / ".next/cache"
        if cache.is_symlink():
            raise ValueError("aliased runtime cache")

        def check(path: Path) -> None:
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                if not path.resolve().is_relative_to(release):
                    raise ValueError("release symlink escape")
            elif not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise ValueError("unsupported release entry")
            if sealed and not path.is_relative_to(cache):
                if info.st_uid != 0:
                    raise ValueError("release ownership mismatch")
                if path != release and info.st_gid != 0:
                    raise ValueError("release ownership mismatch")
                if not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o222:
                    raise ValueError("release is writable")

        def walk_error(exc: OSError) -> None:
            raise exc

        check(release)
        for root, dirs, files in os.walk(release, followlinks=False, onerror=walk_error):
            for name in dirs + files:
                check(Path(root) / name)
        if sealed and stat.S_IMODE(release.stat().st_mode) != 0o550:
            raise ValueError("invalid sealed release mode")
        return resolved_commit
    except (OSError, ValueError, RuntimeError) as exc:
        if isinstance(exc, TakeoverHelperDomainError):
            raise
        raise TakeoverHelperDomainError(
            "release_validation_failed", "Prepared release failed privileged validation."
        ) from exc


def prepare_node_nextjs_release(
    params: dict[str, Any],
    *,
    allowed_bindings: set[tuple[str, str, str]] | None = None,
    source_repositories: dict[tuple[str, str, str], Path] | None = None,
    apps_root: Path = APPS_ROOT,
) -> dict[str, Any]:
    keys = set(params)
    if keys not in (_PREPARE_KEYS, _PREPARE_KEYS | {"source_id"}):
        raise TakeoverHelperDomainError(
            "helper_invalid_request", "Invalid privileged helper parameters."
        )
    project_slug, service_name = _validate_identity(
        params["project_slug"], params["service_name"]
    )
    allowed = (
        allowed_bindings if allowed_bindings is not None else allowed_bindings_from_env()
    )
    unit_name = _validate_binding(project_slug, service_name, params["unit_name"], allowed)
    _validate_repository(params["repository"])
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
    if (
        source_snapshot.get("unit_name") != unit_name
        or source_snapshot.get("user") != user
        or source_snapshot.get("group", "") != group
    ):
        raise TakeoverHelperDomainError(
            "service_configuration_changed",
            "Source service user/group changed before privileged prepare.",
        )
    sources = (
        source_repositories
        if source_repositories is not None
        else trusted_source_repositories_from_env()
    )
    source_id = params.get("source_id")
    if source_id:
        trusted_source = _artifact_source(source_id)
    else:
        provider = LocalSourceProvider(_trusted_local_source_repository, sources)
        try:
            trusted_source = provider.resolve(
                SourceRequest(
                    project_slug=project_slug,
                    service_name=service_name,
                    unit_name=unit_name,
                    repository=params["repository"],
                    exact_commit=exact_commit,
                    user=user,
                    group=group,
                )
            )
        except SourceProviderError as exc:
            raise TakeoverHelperDomainError(exc.code, str(exc)) from exc
    service_root = _ensure_release_directories(
        apps_root,
        project_slug,
        service_name,
        user=user,
        group=group,
    )
    return _build_node_release(
        service_root, apps_root, project_slug, service_name, str(trusted_source),
        exact_commit, root_directory, install_configuration, build_configuration,
        user, group, source_snapshot,
    )


def _build_node_release(
    service_root, apps_root, project_slug, service_name, repository,
    exact_commit, root_directory, install_configuration, build_configuration,
    user, group, source_snapshot,
):
    allocated: list[Path] = []

    try:
        release = _allocate_takeover_release(
            service_root,
            exact_commit,
            user=user,
            group=group,
        )
        allocated.append(release)
        try:
            release = prepare_release(
                project_slug,
                service_name,
                repository,
                exact_commit,
                apps_root=apps_root,
                run_command=lambda argv, timeout=300: _run_as_worker(
                    user,
                    group,
                    argv,
                    writable_path=release,
                    phase="release_git",
                    timeout=timeout,
                ),
                destination=release,
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
            phase = "npm_ci" if command == ["npm", "ci"] else "next_build"
            _run_as_worker(
                user,
                group,
                command,
                cwd=cwd,
                writable_path=release,
                phase=phase,
                npm_cache=True,
                timeout=900,
            )
        _validate_prepared_release(
            release, service_root, root_directory, exact_commit, install_configuration,
            sealed=False,
        )
        runtime_cache = _prepare_next_runtime_cache(cwd, user=user, group=group)
        runtime_gid = _group_id(group, _account(user).pw_gid)
        _seal_release(
            release,
            service_root,
            runtime_gid=runtime_gid,
            writable_paths=(runtime_cache,),
        )
        resolved_commit = _validate_prepared_release(
            release, service_root, root_directory, exact_commit, install_configuration,
            sealed=True,
        )
        allocated.clear()
        return {
            "release_name": release.name,
            "release_path": str(release),
            "resolved_commit": resolved_commit,
            "source_snapshot": source_snapshot,
            "source_fingerprint": fingerprint_snapshot(source_snapshot),
        }
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
    exact_commit = str(params["exact_commit"])
    if not COMMIT.fullmatch(exact_commit):
        raise TakeoverHelperDomainError(
            "invalid_exact_commit", "Takeover requires an exact lowercase commit."
        )
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

    # The release is deliberately inaccessible to digitalafarin-agent after
    # PREPARE. Re-validate the sealed tree here as root immediately before any
    # activation mutation instead of requiring Agent-side traversal.
    _validate_prepared_release(
        release,
        service_root,
        root_directory,
        exact_commit,
        {"lockfile": "package-lock.json"},
        sealed=True,
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


_MANAGED_DELETE_KEYS = {"project_slug", "service_name", "unit_name", "root_directory"}

def delete_managed_service(
    params, *, allowed_bindings=None, apps_root=APPS_ROOT, systemd_root=SYSTEMD_ROOT,
):
    _require_exact_keys(params, _MANAGED_DELETE_KEYS)
    project, service = _validate_identity(params["project_slug"], params["service_name"])
    allowed = allowed_bindings if allowed_bindings is not None else allowed_bindings_from_env()
    unit = _validate_binding(project, service, params["unit_name"], allowed)
    _validate_root_directory(params["root_directory"])
    service_root = _service_root(apps_root, project, service)
    if not service_root.exists() or service_root.is_symlink():
        raise TakeoverHelperDomainError("managed_service_missing", "Managed service root is unavailable.")
    info = service_root.stat()
    if info.st_uid != 0 or info.st_mode & 0o022:
        raise TakeoverHelperDomainError("release_validation_failed", "Unsafe managed service root.")

    dropin = managed_dropin_path(unit, systemd_root=systemd_root)
    if dropin.is_symlink() or not dropin.is_file():
        raise TakeoverHelperDomainError("managed_dropin_missing", "Managed deployment drop-in is unavailable.")

    current = service_root / "current"
    if current.exists() and not current.is_symlink():
        raise TakeoverHelperDomainError("release_validation_failed", "Managed current pointer is not a symlink.")
    if current.is_symlink():
        target = current.resolve(strict=True)
        releases = (service_root / "releases").resolve(strict=True)
        if target.parent != releases or not RELEASE_NAME.fullmatch(target.name):
            raise TakeoverHelperDomainError("release_validation_failed", "Managed current pointer is unsafe.")

    # Restore the pre-Platform systemd configuration before deleting Platform-owned releases.
    remove_managed_dropin(unit, systemd_root=systemd_root)
    daemon_reload()
    restart_takeover_unit(unit)

    if current.is_symlink():
        current.unlink()
    releases_path = service_root / "releases"
    if releases_path.exists():
        if releases_path.is_symlink() or releases_path.resolve().parent != service_root.resolve():
            raise TakeoverHelperDomainError("release_validation_failed", "Managed releases root is unsafe.")
        shutil.rmtree(releases_path)
    shared = service_root / "shared"
    if shared.exists() and not shared.is_symlink() and not any(shared.iterdir()):
        shared.rmdir()
    if service_root.exists() and not any(service_root.iterdir()):
        service_root.rmdir()
    return {"unit_name": unit, "managed_artifacts_removed": True, "unit_deleted": False}


def dispatch_helper_operation(
    operation: str,
    params: dict[str, Any],
    *,
    allowed_bindings: set[tuple[str, str, str]] | None = None,
    source_repositories: dict[tuple[str, str, str], Path] | None = None,
) -> dict[str, Any]:
    managed_operations = {
        "prepare_managed_node_nextjs_release": prepare_managed_node_nextjs_release,
        "activate_managed_release": activate_managed_release,
        "rollback_managed_activation": rollback_managed_activation,
        "rollback_managed_release": rollback_managed_release,
        "prune_managed_releases": prune_managed_releases,
        "delete_managed_service": delete_managed_service,
    }
    if operation in managed_operations:
        return managed_operations[operation](params, allowed_bindings=allowed_bindings)
    if operation == "prepare_node_nextjs_release":
        return prepare_node_nextjs_release(
            params,
            allowed_bindings=allowed_bindings,
            source_repositories=source_repositories,
        )
    if operation == "activate_release":
        return activate_release(params, allowed_bindings=allowed_bindings)
    if operation == "rollback_activation":
        return rollback_activation(params, allowed_bindings=allowed_bindings)
    if operation == "cleanup_release":
        return cleanup_release(params, allowed_bindings=allowed_bindings)
    raise TakeoverHelperDomainError(
        "helper_operation_not_allowed", "Privileged helper operation is not allowlisted."
    )


_MANAGED_PREPARE_KEYS = (_PREPARE_KEYS - {"user", "group"}) | {"runtime", "environment", "volumes"}
_MANAGED_ACTIVATE_KEYS = _ACTIVATE_KEYS - {"source_fingerprint"}
_MANAGED_ROLLBACK_KEYS = _ROLLBACK_KEYS | {"root_directory", "release_name"}


def _managed_context(params, allowed_bindings, apps_root, systemd_root):
    project, service = _validate_identity(params["project_slug"], params["service_name"])
    allowed = allowed_bindings if allowed_bindings is not None else allowed_bindings_from_env()
    unit = _validate_binding(project, service, params["unit_name"], allowed)
    root_directory = _validate_root_directory(params["root_directory"])
    service_root = _service_root(apps_root, project, service)
    if service_root != apps_root.resolve() / project / service:
        raise TakeoverHelperDomainError("release_validation_failed", "Aliased service root.")
    # Every mutation requires trusted parents, not just release preparation.
    for path in (service_root, service_root / "releases"):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise TakeoverHelperDomainError("release_validation_failed", "Unsafe managed release root.")
    dropin = managed_dropin_path(unit, systemd_root=systemd_root)
    if dropin.is_symlink() or not dropin.is_file():
        raise TakeoverHelperDomainError("managed_dropin_missing", "Managed deployment requires an existing drop-in.")
    info = dropin.stat()
    expected = f"[Service]\nWorkingDirectory={service_root / 'current' / root_directory}\n"
    if info.st_uid != 0 or info.st_mode & 0o022 or dropin.read_text() != expected:
        raise TakeoverHelperDomainError("managed_dropin_mismatch", "Managed drop-in does not match the bound working directory.")
    previous = _validate_previous_current(service_root)
    if previous is None or previous.parent != service_root / "releases" or not RELEASE_NAME.fullmatch(previous.name):
        raise TakeoverHelperDomainError("managed_current_missing", "Managed deployment requires a previous release.")
    return project, service, unit, service_root, root_directory, previous


def prepare_managed_node_nextjs_release(
    params, *, allowed_bindings=None, apps_root=APPS_ROOT, systemd_root=SYSTEMD_ROOT,
):
    _require_exact_keys(params, _MANAGED_PREPARE_KEYS)
    project, service, unit, service_root, root_directory, _ = _managed_context(
        params, allowed_bindings, apps_root, systemd_root,
    )
    if params["runtime"] != "node-nextjs":
        raise TakeoverHelperDomainError("managed_runtime_unsupported", "Only node-nextjs managed deployment is supported.")
    if params["environment"] != {}:
        raise TakeoverHelperDomainError("managed_environment_unsupported", "Managed environment updates are not supported.")
    if params["volumes"] != []:
        raise TakeoverHelperDomainError("managed_volumes_unsupported", "Managed volume updates are not supported.")
    repository = _validate_repository(params["repository"])
    trusted = managed_repositories_from_env().get((project, service, unit))
    if trusted is None:
        raise TakeoverHelperDomainError("managed_repository_not_configured", "No trusted managed repository is configured for this binding.")
    if repository != trusted:
        raise TakeoverHelperDomainError("managed_repository_not_allowed", "Repository does not match the trusted binding.")
    commit = params["exact_commit"]
    if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
        raise TakeoverHelperDomainError("invalid_exact_commit", "An exact lowercase commit is required.")
    install, build = params["install_configuration"], params["build_configuration"]
    if not isinstance(install, dict) or not isinstance(build, dict):
        raise TakeoverHelperDomainError("release_validation_failed", "Invalid build configuration.")
    snapshot = inspect_service(unit)
    if snapshot.get("unit_name") != unit:
        raise TakeoverHelperDomainError("service_configuration_changed", "Managed unit identity changed.")
    user, group = snapshot["user"], snapshot["group"]
    account = _account(user)
    if account.pw_uid == 0 or user == "digitalafarin-agent":
        raise TakeoverHelperDomainError("source_user_unsafe", "Unsafe managed build identity.")
    sources = trusted_source_repositories_from_env()
    trusted_source = _trusted_local_source_repository(
        project,
        service,
        unit,
        commit,
        params["repository"],
        user,
        group,
        sources,
    )
    return _build_node_release(
        service_root, apps_root, project, service, str(trusted_source), commit,
        root_directory, install, build, user, group, snapshot,
    )


def activate_managed_release(
    params, *, allowed_bindings=None, apps_root=APPS_ROOT, systemd_root=SYSTEMD_ROOT,
):
    _require_exact_keys(params, _MANAGED_ACTIVATE_KEYS)
    _, _, unit, service_root, root_directory, previous = _managed_context(
        params, allowed_bindings, apps_root, systemd_root,
    )
    release = _release_path(service_root, _validate_release_name(params["release_name"]))
    _validate_prepared_release(
        release, service_root, root_directory, params["exact_commit"],
        {"lockfile": "package-lock.json"}, sealed=True,
    )
    _switch_managed_current(service_root, release, previous, unit, root_directory)
    return {
        "previous_release_name": previous.name, "previous_current_path": str(previous),
        "current_release_name": release.name, "current_path": str(release),
    }


def rollback_managed_activation(
    params, *, allowed_bindings=None, apps_root=APPS_ROOT, systemd_root=SYSTEMD_ROOT,
):
    _require_exact_keys(params, _MANAGED_ROLLBACK_KEYS)
    _, _, unit, service_root, root_directory, current = _managed_context(
        params, allowed_bindings, apps_root, systemd_root,
    )
    if current.name != _validate_release_name(params["release_name"]):
        raise TakeoverHelperDomainError("managed_current_changed", "Current release changed before rollback.")
    previous = _release_path(service_root, _validate_release_name(params["previous_release_name"]))
    try:
        commit = (previous / ".git/HEAD").read_text(encoding="ascii").strip()
        _validate_prepared_release(previous, service_root, root_directory, commit, {"lockfile": "package-lock.json"}, sealed=True)
        _switch_managed_current(service_root, previous, current, unit, root_directory)
    except TakeoverHelperDomainError:
        raise
    except Exception as exc:
        raise TakeoverHelperDomainError("managed_rollback_failed", "Managed rollback failed.") from exc
    return {"previous_release_name": previous.name, "current_path": str(previous)}


def managed_repositories_from_env() -> dict[tuple[str, str, str], str]:
    """Root-admin configuration; never supplied by a helper request or Git config."""
    repositories = {}
    raw = os.environ.get("DIGITALAFARIN_MANAGED_REPOSITORIES", "")
    for item in raw.split(","):
        if not item.strip():
            continue
        parts = [part.strip() for part in item.split("|")]
        if len(parts) != 4 or not all(parts):
            raise TakeoverHelperDomainError("helper_configuration_error", "Invalid managed repository binding.")
        project, service, unit, repository = parts
        _validate_identity(project, service)
        _validate_repository(repository)
        binding = (project, service, unit)
        if binding in repositories:
            raise TakeoverHelperDomainError("helper_configuration_error", "Duplicate managed repository binding.")
        repositories[binding] = repository
    return repositories


def _validate_retained_release(release: Path, service_root: Path, root_directory: str) -> None:
    # Read only a bounded, regular HEAD file, then apply the full seal validation.
    head = release / ".git/HEAD"
    if head.resolve(strict=True) != head or not stat.S_ISREG(head.lstat().st_mode):
        raise TakeoverHelperDomainError("release_validation_failed", "Invalid retained release HEAD.")
    with head.open(encoding="ascii") as stream:
        commit = stream.read(42).strip()
    _validate_prepared_release(
        release, service_root, root_directory, commit,
        {"lockfile": "package-lock.json"}, sealed=True,
    )


def _switch_managed_current(service_root, release, expected_previous, unit, root_directory):
    restore = expected_previous
    try:
        actual_previous = atomic_activate(service_root, release)
        if actual_previous != expected_previous:
            # Preserve the displaced, newer valid activation instead of restoring
            # the stale snapshot. Never restore an arbitrary path returned by a race.
            if actual_previous is not None:
                try:
                    candidate = _release_path(service_root, _validate_release_name(actual_previous.name))
                    if candidate == actual_previous:
                        _validate_retained_release(candidate, service_root, root_directory)
                        restore = candidate
                except (TakeoverHelperDomainError, OSError, ValueError):
                    # A raced target that is unsafe cannot become the recovery target.
                    # Restore the last known valid current and report the race.
                    pass
            raise TakeoverHelperDomainError("managed_current_changed", "Current release changed during activation.")
        restart_takeover_unit(unit)
    except Exception as exc:
        try:
            current = _validate_previous_current(service_root)
            if current not in {release, expected_previous}:
                raise TakeoverHelperDomainError("managed_current_changed", "Current changed again during recovery.")
            _restore_current(service_root, restore)
            restart_takeover_unit(unit)
        except Exception as rollback_exc:
            raise TakeoverHelperDomainError("managed_rollback_failed", "Unable to restore previous managed release safely.") from rollback_exc
        if isinstance(exc, TakeoverHelperDomainError):
            raise
        raise TakeoverHelperDomainError("managed_activation_failed", "Managed activation failed; previous current restored.") from exc


def rollback_managed_release(
    params, *, allowed_bindings=None, apps_root=APPS_ROOT, systemd_root=SYSTEMD_ROOT,
):
    """Activate a retained release; derive the working directory from the drop-in."""
    _require_exact_keys(params, _MANAGED_ACTIVATE_KEYS - {"root_directory"})
    project, service = _validate_identity(params["project_slug"], params["service_name"])
    allowed = allowed_bindings if allowed_bindings is not None else allowed_bindings_from_env()
    unit = _validate_binding(project, service, params["unit_name"], allowed)
    service_root = _service_root(apps_root, project, service)
    dropin = managed_dropin_path(unit, systemd_root=systemd_root)
    if dropin.is_symlink() or not dropin.is_file():
        raise TakeoverHelperDomainError("managed_dropin_missing", "Managed rollback requires the existing drop-in.")
    content = dropin.read_text()
    prefix = f"[Service]\nWorkingDirectory={service_root / 'current'}"
    if not content.startswith(prefix) or not content.endswith("\n"):
        raise TakeoverHelperDomainError("managed_dropin_mismatch", "Invalid managed working directory.")
    suffix = content[len(prefix):-1]
    root_directory = "." if suffix == "" else suffix[1:] if suffix.startswith("/") else ""
    root_directory = _validate_root_directory(root_directory)
    result = activate_managed_release(
        {**params, "root_directory": root_directory}, allowed_bindings=allowed,
        apps_root=apps_root, systemd_root=systemd_root,
    )
    return {**result, "root_directory": root_directory}


def prune_managed_releases(
    params, *, allowed_bindings=None, apps_root=APPS_ROOT, systemd_root=SYSTEMD_ROOT,
):
    """Retain at most five sealed releases, including current and rollback target."""
    _require_exact_keys(params, _MANAGED_ROLLBACK_KEYS)
    project, service, unit, service_root, root_directory, current = _managed_context(
        params, allowed_bindings, apps_root, systemd_root,
    )
    if current.name != _validate_release_name(params["release_name"]):
        raise TakeoverHelperDomainError("managed_current_changed", "Current changed before retention.")
    previous = _release_path(service_root, _validate_release_name(params["previous_release_name"]))
    _validate_retained_release(previous, service_root, root_directory)
    protected = {current, previous}
    candidates = []
    for path in (service_root / "releases").iterdir():
        if not RELEASE_NAME.fullmatch(path.name):
            continue
        # Reject aliases before any deletion, including aliases into another service.
        candidate = _release_path(service_root, path.name)
        info = candidate.lstat()
        if stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o550:
            candidates.append(candidate)
    recent = sorted((p for p in candidates if p not in protected), key=lambda p: tuple(p.name.split("-")[:3]) + (int(p.name.split("-")[3]) if len(p.name.split("-")) == 4 else 1,), reverse=True)
    removed = []
    for path in recent[max(0, 5 - len(protected)):]:
        cleanup_release(
            {"project_slug": project, "service_name": service, "unit_name": unit, "release_name": path.name},
            allowed_bindings=allowed_bindings, apps_root=apps_root,
        )
        removed.append(path.name)
    return {"removed": removed, "retained": sorted(p.name for p in protected | set(recent[:max(0, 5 - len(protected))]))}
