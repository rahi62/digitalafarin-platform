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


def test_client_uses_versioned_allowlisted_protocol(tmp_path):
    socket_path = tmp_path / "helper.sock"
    captured = []
    thread = _serve_once(
        socket_path,
        {"ok": True, "result": {"release_name": "r", "release_path": "/srv/r"}},
        captured,
    )
    client = TakeoverHelperClient(socket_path, timeout=2)

    result = client.prepare_node_nextjs_release({"project_slug": "p"})
    thread.join(2)

    assert result["release_name"] == "r"
    assert captured == [
        {
            "protocol": 1,
            "operation": "prepare_node_nextjs_release",
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
