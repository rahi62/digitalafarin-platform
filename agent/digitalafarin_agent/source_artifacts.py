import io
import os
import re
import tarfile
from pathlib import Path, PurePosixPath


SOURCE_ROOT = Path("/var/lib/digitalafarin-agent/sources")
SOURCE_ID = re.compile(r"^[0-9a-f-]{36}$")


class SourceArtifactError(RuntimeError):
    pass


def store_source_artifact(source_id: str, data: bytes, exact_commit: str, *, root: Path = SOURCE_ROOT) -> Path:
    if not SOURCE_ID.fullmatch(source_id) or not re.fullmatch(r"[0-9a-f]{40}", exact_commit):
        raise SourceArtifactError("invalid source identity")
    if len(data) > 100 * 1024 * 1024:
        raise SourceArtifactError("source artifact exceeds size limit")
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            members = archive.getmembers()
            if not members:
                raise SourceArtifactError("source archive is empty")
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or member.isdev() or member.issym() or member.islnk():
                    raise SourceArtifactError("unsafe source archive")
    except tarfile.TarError as exc:
        raise SourceArtifactError("invalid source archive") from exc
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = root / f"{source_id}.tar.gz"
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
            (root / f"{source_id}.tar.gz").unlink()
        except FileNotFoundError:
            pass
