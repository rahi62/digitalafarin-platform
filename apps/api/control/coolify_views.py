from rest_framework import status
from rest_framework.response import Response

from control.authentication import ServicePrincipalAuthentication
from control.control_views import ControlAPIView, _audit
from control.coolify_client import (
    CoolifyClient,
    CoolifyConfigurationError,
    CoolifyUpstreamError,
)
from control.permissions import require_scope


def _read(call):
    try:
        client = CoolifyClient()
        try:
            return Response(call(client))
        finally:
            client.close()
    except CoolifyConfigurationError:
        return Response(
            {"error": "coolify_not_configured", "message": "Coolify integration is not configured."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except CoolifyUpstreamError:
        return Response(
            {"error": "coolify_unavailable", "message": "Coolify is unavailable."},
            status=status.HTTP_502_BAD_GATEWAY,
        )


def _pick(item, fields):
    if not isinstance(item, dict):
        return {}
    return {field: item[field] for field in fields if field in item}


def _servers(client):
    fields = ("uuid", "name", "description", "ip", "port", "user", "proxy_type")
    return {"items": [_pick(item, fields) for item in client.list_servers()]}


def _projects(client):
    fields = ("uuid", "name", "description")
    return {"items": [_pick(item, fields) for item in client.list_projects()]}


def _resources(client):
    fields = ("uuid", "name", "type", "status", "created_at", "updated_at")
    return {"items": [_pick(item, fields) for item in client.list_resources()]}


class CoolifyReadView(ControlAPIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("coolify:read")]

    event_type = ""

    def respond(self, request, call):
        response = _read(call)
        if response.status_code < 400:
            _audit(request, self.event_type)
        return response


class CoolifyStatusView(CoolifyReadView):
    event_type = "mcp.coolify.status.read"

    def get(self, request):
        return self.respond(request, lambda client: {"version": client.version()})


class CoolifyServerListView(CoolifyReadView):
    event_type = "mcp.coolify.servers.read"

    def get(self, request):
        return self.respond(request, _servers)


class CoolifyProjectListView(CoolifyReadView):
    event_type = "mcp.coolify.projects.read"

    def get(self, request):
        return self.respond(request, _projects)


class CoolifyResourceListView(CoolifyReadView):
    event_type = "mcp.coolify.resources.read"

    def get(self, request):
        return self.respond(request, _resources)
