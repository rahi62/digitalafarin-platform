"""Durable single-worker outbox. Never stores execution context or credentials."""
import json
import os
import stat
import tempfile
from pathlib import Path


class OperationJournal:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> dict | None:
        if not self.path.exists():
            return None
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise RuntimeError('unsafe operation journal permissions')
        return json.loads(self.path.read_text(encoding='utf-8'))

    def write(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.operation-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(record, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            self._sync_directory()
        finally:
            Path(name).unlink(missing_ok=True)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
        self._sync_directory()

    def _sync_directory(self) -> None:
        if os.name == 'posix':
            fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
