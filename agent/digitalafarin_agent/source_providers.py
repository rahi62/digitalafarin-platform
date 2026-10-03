from dataclasses import dataclass
from pathlib import Path


class SourceProviderError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SourceRequest:
    project_slug: str
    service_name: str
    unit_name: str
    repository: str
    exact_commit: str
    user: str
    group: str


class LocalSourceProvider:
    """Adapter for the existing allow-listed local source resolver."""

    def __init__(self, resolver, repositories: dict[tuple[str, str, str], Path]):
        self.resolver = resolver
        self.repositories = repositories

    def resolve(self, request: SourceRequest) -> Path:
        try:
            return self.resolver(
                request.project_slug,
                request.service_name,
                request.unit_name,
                request.exact_commit,
                request.repository,
                request.user,
                request.group,
                self.repositories,
            )
        except RuntimeError as exc:
            code = getattr(exc, "code", "source_provider_failed")
            raise SourceProviderError(code, str(exc)) from exc
