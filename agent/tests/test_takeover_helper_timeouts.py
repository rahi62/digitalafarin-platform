import json
import socket
import threading
import time

import pytest

from digitalafarin_agent.takeover_helper_client import TakeoverHelperClient


@pytest.mark.parametrize("configured_timeout", [30.0, 7.0])
@pytest.mark.parametrize(
    "operation",
    [
        "prepare_node_nextjs_release",
        "activate_release",
        "rollback_activation",
        "cleanup_release",
    ],
)
def test_operation_socket_timeout(monkeypatch, configured_timeout, operation):
    real_socket = socket.socket

    class ResponseSocket:
        def __enter__(self):
            self.sock = real_socket(socket.AF_UNIX, socket.SOCK_STREAM)
            return self

        def __exit__(self, *args):
            self.sock.close()

        def settimeout(self, timeout):
            self.sock.settimeout(timeout)

        def connect(self, path):
            pass

        def sendall(self, raw):
            assert json.loads(raw) == {
                "protocol": 1, "operation": operation, "params": {}
            }

        def shutdown(self, how):
            pass

        def recv(self, size):
            expected = 1200.0 if operation == "prepare_node_nextjs_release" else configured_timeout
            assert self.sock.gettimeout() == expected
            return b'{"ok":true,"result":{"done":true}}\n'

    monkeypatch.setattr(socket, "socket", lambda *args: ResponseSocket())
    client = TakeoverHelperClient() if configured_timeout == 30.0 else TakeoverHelperClient(timeout=configured_timeout)
    assert client.timeout == configured_timeout
    assert getattr(client, operation)({}) == {"done": True}
    assert client.timeout == configured_timeout


def test_prepare_response_after_30_seconds_is_not_helper_unavailable(tmp_path):
    socket_path = tmp_path / "helper.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(socket_path))
        listener.listen(1)
        errors = []

        def respond():
            try:
                conn, _ = listener.accept()
                with conn:
                    while conn.recv(65536):
                        pass
                    time.sleep(31)
                    conn.sendall(b'{"ok":true,"result":{"release_name":"prepared"}}\n')
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected when exercising the pre-fix client timeout.
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        try:
            result = TakeoverHelperClient(socket_path).prepare_node_nextjs_release({})
            assert result == {"release_name": "prepared"}
        finally:
            thread.join(35)
        assert not thread.is_alive()
        assert not errors
