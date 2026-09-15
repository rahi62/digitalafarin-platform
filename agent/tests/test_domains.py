from pathlib import Path
from types import SimpleNamespace

import pytest

from digitalafarin_agent.domains import DomainError, configure_domain, enable_ssl


def test_domain_is_rendered_then_validated_and_atomically_installed(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "digitalafarin_agent.domains.subprocess.run",
        lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    target = configure_domain(
        {"hostname": "app.example.com", "service_port": 3000},
        sites_available=tmp_path / "sites-available",
        sites_enabled=tmp_path / "sites-enabled",
    )

    content = Path(target["config_path"]).read_text(encoding="utf-8")
    assert "server_name app.example.com;" in content
    assert "proxy_pass http://127.0.0.1:3000;" in content
    assert calls == [["nginx", "-t"], ["systemctl", "reload", "nginx.service"]]


def test_ssl_uses_fixed_certbot_arguments(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "digitalafarin_agent.domains.subprocess.run",
        lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    enable_ssl({"hostname": "app.example.com", "email": "ops@example.com"})

    assert calls[0] == ["certbot", "--nginx", "--non-interactive", "--agree-tos", "--redirect", "--email", "ops@example.com", "-d", "app.example.com"]


def test_domain_handlers_reject_configuration_and_flags(tmp_path):
    with pytest.raises(DomainError):
        configure_domain(
            {"hostname": "app.example.com", "service_port": 3000, "config": "include /etc/passwd;"},
            sites_available=tmp_path / "available", sites_enabled=tmp_path / "enabled",
        )
