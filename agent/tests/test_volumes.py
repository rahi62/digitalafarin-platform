from pathlib import Path

import pytest

from digitalafarin_agent.volumes import VolumeError, create_volume


def test_create_volume_is_fixed_root_and_idempotent(tmp_path, monkeypatch):
    ownership = []
    monkeypatch.setattr("digitalafarin_agent.volumes.shutil.chown", lambda path, user, group: ownership.append((path, user, group)))
    payload = {
        "project_slug": "oily",
        "name": "media",
        "owner": "deploy",
        "group": "deploy",
        "mode": "0750",
    }

    first = create_volume(payload, base_path=tmp_path / "volumes")
    marker = Path(first["host_path"]) / "persistent.txt"
    marker.write_text("keep", encoding="utf-8")
    second = create_volume(payload, base_path=tmp_path / "volumes")

    assert first == second
    assert marker.read_text(encoding="utf-8") == "keep"
    assert (Path(first["host_path"]).stat().st_mode & 0o777) == 0o750
    assert ownership[-1][1:] == ("deploy", "deploy")


def test_create_volume_rejects_traversal_and_unknown_fields(tmp_path):
    with pytest.raises(VolumeError):
        create_volume(
            {"project_slug": "../etc", "name": "data", "owner": "root", "group": "root", "mode": "0750"},
            base_path=tmp_path,
        )
    with pytest.raises(VolumeError):
        create_volume(
            {"project_slug": "oily", "name": "data", "owner": "root", "group": "root", "mode": "0750", "path": "/etc"},
            base_path=tmp_path,
        )
