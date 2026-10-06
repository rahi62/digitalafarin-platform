import grp
import json
import os
import pwd
import socket
import socketserver
import struct
from pathlib import Path
from typing import Any

from .takeover_helper import (
    TakeoverHelperDomainError,
    allowed_bindings_from_env,
    dispatch_helper_operation,
    trusted_source_repositories_from_env,
)


DEFAULT_SOCKET_PATH = Path(
    os.environ.get(
        "DIGITALAFARIN_TAKEOVER_HELPER_SOCKET",
        "/run/digitalafarin-takeover/helper.sock",
    )
)
MAX_REQUEST_BYTES = 256 * 1024


class _HelperServer(socketserver.UnixStreamServer):
    allow_reuse_address = False

    def __init__(
        self,
        socket_path: Path,
        *,
        allowed_peer_user: str,
        socket_group: str,
        allowed_bindings: set[tuple[str, str, str]],
        source_repositories: dict[tuple[str, str, str], Path],
    ) -> None:
        self.allowed_peer_uid = pwd.getpwnam(allowed_peer_user).pw_uid
        self.socket_gid = grp.getgrnam(socket_group).gr_gid
        self.allowed_bindings = allowed_bindings
        self.source_repositories = source_repositories
        super().__init__(str(socket_path), _HelperHandler)
        os.chown(socket_path, 0, self.socket_gid)
        os.chmod(socket_path, 0o660)


class _HelperHandler(socketserver.StreamRequestHandler):
    server: _HelperServer

    def _peer_uid(self) -> int:
        raw = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        _pid, uid, _gid = struct.unpack("3i", raw)
        return uid

    def _write(self, payload: dict[str, Any]) -> None:
        encoded = (json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n").encode(
            "utf-8"
        )
        self.wfile.write(encoded)
        self.wfile.flush()

    def handle(self) -> None:
        try:
            peer_uid = self._peer_uid()
        except OSError:
            self._write(
                {
                    "ok": False,
                    "error": {
                        "code": "helper_peer_rejected",
                        "message": "Unable to authenticate local helper peer.",
                    },
                }
            )
            return
        if peer_uid not in {0, self.server.allowed_peer_uid}:
            self._write(
                {
                    "ok": False,
                    "error": {
                        "code": "helper_peer_rejected",
                        "message": "Local helper peer is not authorized.",
                    },
                }
            )
            return

        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
            self._write(
                {
                    "ok": False,
                    "error": {
                        "code": "helper_invalid_request",
                        "message": "Helper request exceeded protocol limits.",
                    },
                }
            )
            return
        try:
            request = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write(
                {
                    "ok": False,
                    "error": {
                        "code": "helper_invalid_request",
                        "message": "Invalid helper request.",
                    },
                }
            )
            return
        if (
            not isinstance(request, dict)
            or set(request) != {"protocol", "operation", "params"}
            or request.get("protocol") != 1
            or not isinstance(request.get("operation"), str)
            or not isinstance(request.get("params"), dict)
        ):
            self._write(
                {
                    "ok": False,
                    "error": {
                        "code": "helper_invalid_request",
                        "message": "Invalid helper request.",
                    },
                }
            )
            return
        try:
            result = dispatch_helper_operation(
                request["operation"],
                request["params"],
                allowed_bindings=self.server.allowed_bindings,
                source_repositories=self.server.source_repositories,
            )
        except TakeoverHelperDomainError as exc:
            self._write(
                {
                    "ok": False,
                    "error": {"code": exc.code, "message": str(exc)},
                }
            )
            return
        except Exception:
            self._write(
                {
                    "ok": False,
                    "error": {
                        "code": "helper_internal_error",
                        "message": "Privileged takeover helper failed.",
                    },
                }
            )
            return
        self._write({"ok": True, "result": result})


def main() -> None:
    socket_path = DEFAULT_SOCKET_PATH
    if not socket_path.is_absolute():
        raise SystemExit("Takeover helper socket path must be absolute.")
    parent = socket_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink():
        raise SystemExit("Takeover helper runtime directory cannot be a symlink.")
    if socket_path.exists() or socket_path.is_symlink():
        if socket_path.is_socket():
            socket_path.unlink()
        else:
            raise SystemExit("Refusing to replace non-socket helper path.")

    allowed_peer_user = os.environ.get(
        "DIGITALAFARIN_TAKEOVER_HELPER_PEER_USER", "digitalafarin-agent"
    )
    socket_group = os.environ.get(
        "DIGITALAFARIN_TAKEOVER_HELPER_SOCKET_GROUP", "digitalafarin-agent"
    )
    allowed_bindings = allowed_bindings_from_env()
    if not allowed_bindings:
        raise SystemExit("No takeover project/service/unit bindings are allowlisted.")
    # Local source repositories are an optional fallback. GitHub App source bundles
    # are delivered as source_id artifacts and do not require a persistent checkout
    # for every allowlisted binding.
    source_repositories = trusted_source_repositories_from_env()

    old_umask = os.umask(0o077)
    try:
        with _HelperServer(
            socket_path,
            allowed_peer_user=allowed_peer_user,
            socket_group=socket_group,
            allowed_bindings=allowed_bindings,
            source_repositories=source_repositories,
        ) as server:
            server.serve_forever(poll_interval=0.5)
    finally:
        os.umask(old_umask)
        try:
            if socket_path.is_socket():
                socket_path.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
