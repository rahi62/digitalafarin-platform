import json
import socket
import threading
from pathlib import Path

import pytest

from digitalafarin_agent.takeover_helper_client import (
    TakeoverHelperClient,
    TakeoverHelperError,
)


def _serve_once(socket_path: Path, response: dict, captured: list[dict]):
    ready = threading.Event()

    def server():
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.bind(str(socket_path))
            sock.listen(1)
            ready.set()
            conn, _ = sock.accept()
            with conn:
                data = b""
                while b"\n" not in data:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                captured.append(json.loads(data.split(b"\n", 1)[0].decode("utf-8")))
                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert ready.wait(2)
    return thread


@pytest.mark.parametrize("operation", [
    "prepare_node_nextjs_release", "prepare_managed_node_nextjs_release",
    "activate_managed_release", "rollback_managed_activation",
    "rollback_managed_release", "prune_managed_releases",
])
def test_client_uses_versioned_allowlisted_protocol(tmp_path, operation):
    socket_path = tmp_path / "helper.sock"
    captured = []
    thread = _serve_once(
        socket_path,
        {"ok": True, "result": {"release_name": "r", "release_path": "/srv/r"}},
        captured,
    )
    client = TakeoverHelperClient(socket_path, timeout=2)

    result = getattr(client, operation)({"project_slug": "p"})
    thread.join(2)

    assert result["release_name"] == "r"
    assert captured == [
        {
            "protocol": 1,
            "operation": operation,
            "params": {"project_slug": "p"},
        }
    ]


def test_client_preserves_stable_helper_domain_error(tmp_path):
    socket_path = tmp_path / "helper.sock"
    captured = []
    thread = _serve_once(
        socket_path,
        {
            "ok": False,
            "error": {"code": "helper_unit_not_allowed", "message": "blocked"},
        },
        captured,
    )
    client = TakeoverHelperClient(socket_path, timeout=2)

    with pytest.raises(TakeoverHelperError) as exc:
        client.activate_release({"unit_name": "oily.service"})
    thread.join(2)
    assert exc.value.code == "helper_unit_not_allowed"


def test_client_streams_bounded_progress_before_terminal_result(tmp_path):
    socket_path = tmp_path / "helper.sock"
    ready = threading.Event()

    def server():
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.bind(str(socket_path))
            sock.listen(1)
            ready.set()
            conn, _ = sock.accept()
            with conn:
                while conn.recv(65536):
                    pass
                conn.sendall(b'{"progress":{"stage":"cloning"}}\n')
                conn.sendall(b'{"progress":{"stage":"health_check"}}\n')
                conn.sendall(b'{"ok":true,"result":{"done":true}}\n')

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert ready.wait(2)
    stages = []
    result = TakeoverHelperClient(socket_path, timeout=2).provision_service({}, on_progress=stages.append)
    thread.join(2)
    assert result == {"done": True}
    assert stages == ["cloning", "health_check"]
