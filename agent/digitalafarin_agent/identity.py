import os
from pathlib import Path


class AgentIdentityStore:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> str | None:
        if not self.path.exists():
            return None
        return self.path.read_text(encoding="utf-8").strip() or None

    def write(self, token: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, (token.strip() + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        os.chmod(self.path, 0o600)
