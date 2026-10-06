import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from digitalafarin_agent.takeover_worker import (
    TakeoverWorkerError,
    run_takeover_worker,
)


def _identity(monkeypatch):
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_worker.pwd.getpwnam",
        lambda user: SimpleNamespace(pw_name=user, pw_uid=1000, pw_gid=1000),
    )
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_worker.grp.getgrnam",
        lambda group: SimpleNamespace(gr_name=group, gr_gid=33),
    )


def test_worker_uses_internally_generated_hardened_unit_and_exact_identity(monkeypatch):
    _identity(monkeypatch)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr("digitalafarin_agent.takeover_worker.subprocess.run", fake_run)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_worker.secrets.token_hex", lambda _size: "0123456789abcdef"
    )

    result = run_takeover_worker(
        phase="source_verify",
        user="deploy",
        group="www-data",
        argv=["git", "-C", "/opt/digitalafarin-platform", "rev-parse", "HEAD"],
        timeout=30,
    )

    assert result == "ok"
    argv, kwargs = calls[0]
    assert argv[0] == "/usr/bin/systemd-run"
    assert "--unit=digitalafarin-takeover-worker-0123456789abcdef.service" in argv
    assert "--property=Type=oneshot" in argv
    assert "--property=User=deploy" in argv
    assert "--property=Group=www-data" in argv
    assert "--property=SupplementaryGroups=" in argv
    assert "--property=NoNewPrivileges=yes" in argv
    assert "--property=PrivateUsers=yes" in argv
    assert "--property=ProtectSystem=strict" in argv
    assert "--property=CapabilityBoundingSet=" in argv
    assert "--property=AmbientCapabilities=" in argv
    assert not any(item.startswith("--property=RuntimeMaxSec=") for item in argv)
    assert kwargs["timeout"] == 30
    assert not any(item.startswith("--property=ReadWritePaths=") for item in argv)
    assert "setpriv" not in argv
    assert "runuser" not in argv
    assert "su" not in argv
    assert argv[-5:] == [
        "git",
        "-C",
        "/opt/digitalafarin-platform",
        "rev-parse",
        "HEAD",
    ]
    assert kwargs["shell"] is False
    assert kwargs["env"] == {"PATH": "/usr/local/bin:/usr/bin:/bin"}


def test_build_worker_exposes_only_exact_release_and_isolates_npm_cache(
    tmp_path, monkeypatch
):
    _identity(monkeypatch)
    calls = []
    release = tmp_path / "releases" / "20260920-120000-aaaaaaa"
    cwd = release / "apps" / "web"
    cwd.mkdir(parents=True)
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_worker.subprocess.run",
        lambda argv, **kwargs: calls.append((argv, kwargs))
        or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    run_takeover_worker(
        phase="npm_ci",
        user="deploy",
        group="www-data",
        argv=["npm", "ci"],
        cwd=cwd,
        writable_path=release,
        npm_cache=True,
        timeout=900,
    )

    argv = calls[0][0]
    assert f"--property=ReadWritePaths={release.resolve()}" in argv
    assert f"--working-directory={cwd.resolve()}" in argv
    assert "--setenv=NPM_CONFIG_CACHE=/tmp/.npm-digitalafarin-takeover" in argv
    assert not any("/opt/digitalafarin-platform" in item for item in argv)


def test_worker_failure_is_generic_but_journal_diagnostic_is_bounded_and_redacted(
    monkeypatch, caplog
):
    _identity(monkeypatch)
    secret = "token=super-secret-value"
    stderr = "x" * 5000 + "\nAuthorization: Bearer abc.def\n" + secret
    monkeypatch.setattr(
        "digitalafarin_agent.takeover_worker.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=23, stdout="", stderr=stderr
        ),
    )

    with caplog.at_level(logging.WARNING), pytest.raises(TakeoverWorkerError) as exc:
        run_takeover_worker(
            phase="next_build",
            user="deploy",
            group="www-data",
            argv=["npm", "run", "build"],
            timeout=900,
        )

    assert str(exc.value) == "Takeover worker command failed."
    message = caplog.records[-1].getMessage()
    assert "phase=next_build" in message
    assert "unit=digitalafarin-takeover-worker-" in message
    assert "status=23" in message
    assert "super-secret-value" not in message
    assert "abc.def" not in message
    assert "[REDACTED]" in message
    assert len(message) < 2600


@pytest.mark.parametrize("field,value", [("user", "root"), ("group", "missing")])
def test_worker_rejects_unvalidated_identity(field, value, monkeypatch):
    _identity(monkeypatch)
    if field == "group":
        monkeypatch.setattr(
            "digitalafarin_agent.takeover_worker.grp.getgrnam",
            lambda _group: (_ for _ in ()).throw(KeyError()),
        )
    kwargs = {"user": "deploy", "group": "www-data"}
    kwargs[field] = value

    with pytest.raises(TakeoverWorkerError):
        run_takeover_worker(
            phase="source_verify", argv=["git", "rev-parse", "HEAD"], **kwargs
        )
