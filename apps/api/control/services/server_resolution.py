import uuid

from control.models import Server


class ServerResolutionError(RuntimeError):
    code = "server_not_found"


class DefaultServerNotConfigured(ServerResolutionError):
    code = "default_server_not_configured"


def resolve_server(identifier: str) -> Server:
    if identifier == "default":
        server = Server.objects.filter(is_active=True, is_default=True).first()
        if server is None:
            raise DefaultServerNotConfigured("Default server is not configured")
        return server
    try:
        public_id = uuid.UUID(identifier)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ServerResolutionError("Server does not exist") from exc
    try:
        return Server.objects.get(public_id=public_id, is_active=True)
    except Server.DoesNotExist as exc:
        raise ServerResolutionError("Server does not exist") from exc
