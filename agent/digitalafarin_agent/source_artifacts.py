import os
import re
from pathlib import Path


SOURCE_ROOT = Path("/var/lib/digitalafarin-agent/sources")
SOURCE_ID = re.compile(r"^[0-9a-f-]{36}$")


class SourceArtifactError(RuntimeError):
    pass


def store_source_artifact(source_id: str, data: bytes, exact_commit: str, *, root: Path = SOURCE_ROOT) -> Path:
    if not SOURCE_ID.fullmatch(source_id) or not re.fullmatch(r"[0-9a-f]{40}", exact_commit):
        raise SourceArtifactError("invalid source identity")
    if len(data) > 100 * 1024 * 1024:
        raise SourceArtifactError("source artifact exceeds size limit")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = root / f"{source_id}.bundle"
    temporary = root / f".{source_id}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def remove_source_artifact(source_id: str, *, root: Path = SOURCE_ROOT) -> None:
    if SOURCE_ID.fullmatch(source_id):
        try:
            (root / f"{source_id}.bundle").unlink()
        except FileNotFoundError:
            pass
