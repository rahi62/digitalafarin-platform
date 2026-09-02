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
