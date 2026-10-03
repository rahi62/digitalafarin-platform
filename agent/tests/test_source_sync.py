from pathlib import Path

import pytest

from digitalafarin_agent import takeover_helper as h
from digitalafarin_agent.takeover_worker import TakeoverWorkerError


IDENTITY = ("project", "web", "web.service")
REPOSITORY = "https://github.com/example/repo.git"
COMMIT = "a" * 40


def test_trusted_source_syncs_exact_commit_before_build(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    calls = []

    def worker(*, phase, user, group, argv, timeout, **kwargs):
        calls.append((phase, argv))
        if argv[-3:] == ["remote", "get-url", "origin"]:
            return REPOSITORY
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return COMMIT
        return ""

    monkeypatch.setattr(h, "run_takeover_worker", worker)

    result = h._trusted_local_source_repository(
        *IDENTITY,
        COMMIT,
        REPOSITORY,
        "deploy",
        "www-data",
        {IDENTITY: source},
    )

    assert result == source.resolve()
    assert [call[0] for call in calls] == [
        "source_verify",
        "source_sync",
        "source_sync",
        "source_verify",
    ]
    assert calls[1][1][-5:] == ["fetch", "--no-tags", "origin", COMMIT]
    assert calls[2][1][-3:] == ["checkout", "--detach", COMMIT]


def test_trusted_source_rejects_wrong_origin_before_fetch(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    calls = []

    def worker(*, phase, user, group, argv, timeout, **kwargs):
        calls.append(argv)
        return "https://github.com/example/other.git"

    monkeypatch.setattr(h, "run_takeover_worker", worker)

    with pytest.raises(h.TakeoverHelperDomainError) as exc:
        h._trusted_local_source_repository(
            *IDENTITY,
            COMMIT,
            REPOSITORY,
            "deploy",
            "www-data",
            {IDENTITY: source},
        )

    assert exc.value.code == "managed_repository_not_allowed"
    assert len(calls) == 1


def test_trusted_source_sync_failure_is_explicit(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()

    def worker(*, phase, user, group, argv, timeout, **kwargs):
        if argv[-3:] == ["remote", "get-url", "origin"]:
            return REPOSITORY
        if "fetch" in argv:
            raise TakeoverWorkerError("fetch failed")
        return ""

    monkeypatch.setattr(h, "run_takeover_worker", worker)

    with pytest.raises(h.TakeoverHelperDomainError) as exc:
        h._trusted_local_source_repository(
            *IDENTITY,
            COMMIT,
            REPOSITORY,
            "deploy",
            "www-data",
            {IDENTITY: source},
        )

    assert exc.value.code == "source_sync_failed"


def test_trusted_source_rejects_head_mismatch_after_sync(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()

    def worker(*, phase, user, group, argv, timeout, **kwargs):
        if argv[-3:] == ["remote", "get-url", "origin"]:
            return REPOSITORY
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return "b" * 40
        return ""

    monkeypatch.setattr(h, "run_takeover_worker", worker)

    with pytest.raises(h.TakeoverHelperDomainError) as exc:
        h._trusted_local_source_repository(
            *IDENTITY,
            COMMIT,
            REPOSITORY,
            "deploy",
            "www-data",
            {IDENTITY: source},
        )

    assert exc.value.code == "source_sync_failed"
