import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class ReleaseError(RuntimeError):
    pass


def _run(argv: list[str], timeout: int = 300) -> None:
    try:
        subprocess.run(
            argv,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ReleaseError("release command failed") from exc


def resolve_exact_commit(repository: str, ref: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", ref):
        raise ReleaseError("invalid Git ref")
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", "--refs", repository, ref, f"refs/heads/{ref}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ReleaseError("unable to resolve Git ref") from exc
    matches = [line.split()[0] for line in result.stdout.splitlines() if line.split()]
    if not matches or not COMMIT.fullmatch(matches[0]):
        raise ReleaseError("Git ref did not resolve to an exact commit")
    return matches[0]


def prepare_release(
    project_slug: str,
    service_name: str,
    repository: str,
    exact_commit: str,
    *,
    apps_root: Path = Path("/srv/digitalafarin/apps"),
    timestamp: str | None = None,
    run_command=_run,
    prepare_destination=None,
) -> Path:
    if not SLUG.fullmatch(project_slug) or not SLUG.fullmatch(service_name):
        raise ReleaseError("invalid release identity")
    if not COMMIT.fullmatch(exact_commit):
        raise ReleaseError("commit must be an exact SHA-1")
    root = apps_root.resolve()
    service_root = (root / project_slug / service_name).resolve()
    if not service_root.is_relative_to(root):
        raise ReleaseError("release path escapes base")
    releases = service_root / "releases"
    (service_root / "shared").mkdir(parents=True, exist_ok=True)
    releases.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base_name = f"{stamp}-{exact_commit[:7]}"
    release = releases / base_name
    sequence = 2
    while release.exists():
        release = releases / f"{base_name}-{sequence}"
        sequence += 1
    if prepare_destination is not None:
        prepare_destination(release)
    run_command(["git", "clone", "--no-checkout", "--", repository, str(release)], timeout=300)
    run_command(["git", "-C", str(release), "checkout", "--detach", exact_commit], timeout=300)
    return release


def atomic_activate(service_root: Path, release: Path) -> Path | None:
    root = service_root.resolve()
    release = release.resolve()
    releases = (root / "releases").resolve()
    if not release.is_relative_to(releases) or not release.is_dir():
        raise ReleaseError("activation target is not a managed release")
    current = root / "current"
    previous = current.resolve() if current.is_symlink() else None
    temporary = root / ".current.next"
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(release)
    os.replace(temporary, current)
    return previous


def rollback(service_root: Path, previous_release: Path | None) -> None:
    if previous_release is None:
        raise ReleaseError("no previous release")
    atomic_activate(service_root, previous_release)


def cleanup_releases(service_root: Path, *, keep: int = 5, protected: set[Path]) -> list[Path]:
    releases = service_root.resolve() / "releases"
    if not releases.is_dir():
        return []
    protected_resolved = {path.resolve() for path in protected}
    candidates = [
        path for path in sorted(releases.iterdir(), key=lambda item: item.name, reverse=True)
        if path.is_dir() and not path.is_symlink() and path.resolve() not in protected_resolved
    ]
    removed = []
    for path in candidates[max(0, keep):]:
        shutil.rmtree(path)
        removed.append(path)
    return removed
