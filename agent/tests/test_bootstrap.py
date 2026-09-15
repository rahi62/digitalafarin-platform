from pathlib import Path

from digitalafarin_agent.bootstrap import bootstrap_server


def test_bootstrap_creates_fixed_directories_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("digitalafarin_agent.bootstrap.platform.freedesktop_os_release", lambda: {"ID": "ubuntu", "VERSION_ID": "24.04"})
    monkeypatch.setattr("digitalafarin_agent.bootstrap.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("digitalafarin_agent.bootstrap.psutil.virtual_memory", lambda: type("M", (), {"total": 4 * 1024**3})())
    monkeypatch.setattr("digitalafarin_agent.bootstrap.shutil.disk_usage", lambda path: type("D", (), {"total": 100, "used": 20, "free": 80})())

    first = bootstrap_server({}, srv_root=tmp_path / "srv" )
    second = bootstrap_server({}, srv_root=tmp_path / "srv")

    assert first["overall"] == "ready"
    assert second["overall"] == "ready"
    assert {p.name for p in (tmp_path / "srv" / "digitalafarin").iterdir()} == {"apps", "volumes", "backups"}
    assert all(item["status"] == "ready" for item in second["checks"])


def test_bootstrap_reports_unsupported_os_and_missing_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("digitalafarin_agent.bootstrap.platform.freedesktop_os_release", lambda: {"ID": "unknown", "VERSION_ID": "1"})
    monkeypatch.setattr("digitalafarin_agent.bootstrap.shutil.which", lambda name: None)
    monkeypatch.setattr("digitalafarin_agent.bootstrap.psutil.virtual_memory", lambda: type("M", (), {"total": 512 * 1024**2})())
    monkeypatch.setattr("digitalafarin_agent.bootstrap.shutil.disk_usage", lambda path: type("D", (), {"total": 100, "used": 95, "free": 5})())

    result = bootstrap_server({}, srv_root=tmp_path / "srv")

    assert result["overall"] == "blocked"
    statuses = {item["name"]: item["status"] for item in result["checks"]}
    assert statuses["os"] == "blocked"
    assert statuses["git"] == "blocked"
    assert statuses["disk"] == "blocked"
