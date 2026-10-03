from pathlib import Path

import pytest

from digitalafarin_agent.source_providers import (
    LocalSourceProvider,
    SourceProviderError,
    SourceRequest,
)


def request():
    return SourceRequest(
        project_slug="project",
        service_name="web",
        unit_name="web.service",
        repository="https://github.com/example/repo.git",
        exact_commit="a" * 40,
        user="deploy",
        group="www-data",
    )


def test_local_provider_preserves_existing_resolver_contract(tmp_path):
    source = tmp_path / "source"
    calls = []

    def resolver(*args):
        calls.append(args)
        return source

    repositories = {("project", "web", "web.service"): source}
    provider = LocalSourceProvider(resolver, repositories)

    assert provider.resolve(request()) == source
    assert calls == [(
        "project", "web", "web.service", "a" * 40,
        "https://github.com/example/repo.git", "deploy", "www-data", repositories,
    )]


def test_local_provider_normalizes_domain_error_without_hiding_code():
    class DomainError(RuntimeError):
        code = "managed_repository_not_allowed"

    def resolver(*_args):
        raise DomainError("repository mismatch")

    provider = LocalSourceProvider(resolver, {})

    with pytest.raises(SourceProviderError) as exc:
        provider.resolve(request())

    assert exc.value.code == "managed_repository_not_allowed"
    assert str(exc.value) == "repository mismatch"
