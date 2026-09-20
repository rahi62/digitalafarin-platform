from configparser import ConfigParser
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_unit(name: str) -> ConfigParser:
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(REPO_ROOT / "infra" / "systemd" / name)
    return parser


def test_tunnel_unit_can_read_service_users_official_profile_directory():
    unit = load_unit("digitalafarin-platform-mcp-tunnel.service")

    assert unit["Service"]["User"] == "digitalafarin-mcp"
    assert unit["Service"]["ProtectHome"] == "read-only"


def test_tunnel_unit_loads_runtime_key_from_protected_service_file():
    unit = load_unit("digitalafarin-platform-mcp-tunnel.service")

    assert unit["Service"]["EnvironmentFile"] == (
        "/home/digitalafarin-mcp/.config/tunnel-client/digitalafarin-vps.env"
    )


def test_agent_unit_keeps_non_root_identity_and_limits_writes_to_managed_roots():
    unit = load_unit("digitalafarin-platform-agent.service")

    assert unit["Service"]["User"] == "digitalafarin-agent"
    assert unit["Service"]["Group"] == "digitalafarin-agent"
    read_write_paths = unit["Service"]["ReadWritePaths"].split()
    assert "/var/lib/digitalafarin-agent" in read_write_paths
    assert "/srv/digitalafarin" in read_write_paths
    assert "/srv" not in read_write_paths


def test_tmpfiles_precreates_only_platform_managed_srv_root():
    config = (REPO_ROOT / "infra" / "tmpfiles.d" / "digitalafarin-platform.conf").read_text(encoding="utf-8")

    assert "d /srv/digitalafarin 0750 digitalafarin-agent digitalafarin-agent -" in config
    assert "/srv/digitalafarin/apps" not in config
    assert "/srv/digitalafarin/volumes" not in config
    assert "/srv/digitalafarin/backups" not in config


def test_takeover_helper_is_root_only_but_socket_scoped_and_unit_allowlisted():
    unit = load_unit("digitalafarin-platform-takeover-helper.service")

    assert unit["Service"]["User"] == "root"
    assert unit["Service"]["Group"] == "digitalafarin-agent"
    assert unit["Service"]["NoNewPrivileges"] == "yes"
    assert unit["Service"]["ProtectSystem"] == "strict"
    assert unit["Service"]["ProtectHome"] == "yes"
    assert unit["Service"]["PrivateTmp"] == "yes"
    assert unit["Service"]["ProtectKernelTunables"] == "yes"
    assert unit["Service"]["ProtectKernelModules"] == "yes"
    assert unit["Service"]["ProtectControlGroups"] == "yes"
    assert unit["Service"]["LockPersonality"] == "yes"
    assert unit["Service"]["RuntimeDirectory"] == "digitalafarin-takeover"
    environment = unit["Service"]["Environment"]
    assert "DIGITALAFARIN_TAKEOVER_HELPER_SOCKET=/run/digitalafarin-takeover/helper.sock" in environment
    assert "DIGITALAFARIN_TAKEOVER_HELPER_PEER_USER=digitalafarin-agent" in environment
    assert "DIGITALAFARIN_TAKEOVER_ALLOWED_BINDINGS=digitalafarin-platform|platform-web|digitalafarin-platform-web.service" in environment
    read_write_paths = unit["Service"]["ReadWritePaths"].split()
    assert "/srv/digitalafarin/apps" in read_write_paths
    assert "/etc/systemd/system" in read_write_paths
    assert unit["Service"]["ExecStartPre"] == "/usr/bin/test -x /usr/bin/systemd-run"
    assert "setpriv" not in unit["Service"]["ExecStartPre"]
