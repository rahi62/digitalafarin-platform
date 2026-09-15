from pathlib import Path
from types import SimpleNamespace

import pytest

from digitalafarin_agent.postgres import DatabaseError, create_database, restore_database


def test_create_database_uses_fixed_psql_argv_and_stdin(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "digitalafarin_agent.postgres.subprocess.run",
        lambda argv, **kwargs: calls.append((argv, kwargs)) or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    result = create_database({"database_name": "oily", "username": "oily_app", "password": "sentinel-secret"})

    assert result == {"created": True}
    assert calls[0][0] == ["psql", "--no-psqlrc", "--set=ON_ERROR_STOP=1", "--dbname=postgres"]
    assert "sentinel-secret" not in " ".join(calls[0][0])
    assert "CREATE ROLE" in calls[0][1]["input"]
    assert calls[0][1]["shell"] is False


def test_restore_uses_managed_backup_root(monkeypatch, tmp_path):
    backup = tmp_path / "backups" / "oily.dump"
    backup.parent.mkdir()
    backup.write_bytes(b"fixture")
    calls = []
    monkeypatch.setattr(
        "digitalafarin_agent.postgres.subprocess.run",
        lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    restore_database(
        {"database_name": "oily", "username": "oily_app", "backup_name": "oily.dump"},
        backup_root=tmp_path / "backups",
    )

    assert calls[0] == ["pg_restore", "--exit-on-error", "--no-owner", "--role", "oily_app", "--dbname", "oily", str(backup)]


def test_database_operations_reject_identifiers_and_arbitrary_sql(tmp_path):
    with pytest.raises(DatabaseError):
        create_database({"database_name": "oily;drop", "username": "app", "password": "secret"})
    with pytest.raises(DatabaseError):
        restore_database(
            {"database_name": "oily", "username": "app", "backup_name": "ok.dump", "sql": "select 1"},
            backup_root=tmp_path,
        )
