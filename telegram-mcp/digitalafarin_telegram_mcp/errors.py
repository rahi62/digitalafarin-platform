from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPDomainError(Exception):
    code: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"ok": False, "error": self.code, "message": self.message}
        if self.data:
            result["data"] = self.data
        return result
