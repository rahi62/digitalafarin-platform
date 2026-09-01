from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.control_serializers import (
    AuditReadSerializer,
    MetricsReadSerializer,
    ServerReadSerializer,
    ServiceReadSerializer,
)
from control.models import AuditEvent, Server
from control.permissions import require_scope
from control.services.server_resolution import (
    DefaultServerNotConfigured,
    ServerResolutionError,
    resolve_server,
)


def _error(exc):
    if isinstance(exc, DefaultServerNotConfigured):
        return Response(
            {
                "error": exc.code,
                "message": "Default server is not configured.",
            },
            status=status.HTTP_409_CONFLICT,
        )
    return Response(
        {
            "error": "server_not_found",
            "message": "The requested server does not exist.",
        },
        status=status.HTTP_404_NOT_FOUND,
    )


def _audit(request, event_type: str, server=None, metadata=None):
    AuditEvent.objects.create(
        event_type=event_type,
        target_type="server" if server else "control",
        target_id=str(server.public_id) if server else "",
        actor=request.user.name,
        metadata=metadata or {},
    )


class ControlAPIView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]


class ServerListView(ControlAPIView):
    permission_classes = [require_scope("servers:read")]

    def get(self, request):
        items = Server.objects.filter(is_active=True).order_by("name")
        _audit(request, "mcp.servers.read", metadata={"count": items.count()})
        return Response({"items": ServerReadSerializer(items, many=True).data})


class ServerDetailView(ControlAPIView):
    permission_classes = [require_scope("servers:read")]

    def get(self, request, server_id):
        try:
            server = resolve_server(server_id)
        except ServerResolutionError as exc:
            return _error(exc)
        _audit(request, "mcp.servers.read", server)
        return Response(ServerReadSerializer(server).data)


class ServerMetricsView(ControlAPIView):
    permission_classes = [require_scope("metrics:read")]

    def get(self, request, server_id):
        try:
            server = resolve_server(server_id)
        except ServerResolutionError as exc:
            return _error(exc)
        if server.last_seen_at is None:
            return Response(
                {
                    "error": "metrics_unavailable",
                    "message": "No metrics snapshot is available.",
                },
                status=status.HTTP_409_CONFLICT,
            )
        if server.status == "offline":
            return Response(
                {
                    "error": "server_offline",
                    "message": "Server has not reported recently.",
                    "last_seen_at": server.last_seen_at,
                },
                status=status.HTTP_409_CONFLICT,
            )
        _audit(request, "mcp.metrics.read", server)
        return Response(MetricsReadSerializer(server).data)


class ServiceListView(ControlAPIView):
    permission_classes = [require_scope("services:read")]

    def get(self, request, server_id):
        try:
            server = resolve_server(server_id)
        except ServerResolutionError as exc:
            return _error(exc)
        qs = server.services.all()
        state = request.query_params.get("status")
        if state:
            qs = qs.filter(active_state=state)
        metadata = {"count": qs.count()}
        if state:
            metadata["status"] = state
        _audit(request, "mcp.services.read", server, metadata)
        return Response({"items": ServiceReadSerializer(qs, many=True).data})


class ServiceDetailView(ControlAPIView):
    permission_classes = [require_scope("services:read")]

    def get(self, request, server_id, unit_name):
        try:
            server = resolve_server(server_id)
        except ServerResolutionError as exc:
            return _error(exc)
        service = server.services.filter(unit_name=unit_name).first()
        if service is None:
            return Response(
                {
                    "error": "service_not_found",
                    "message": "The requested service does not exist.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        _audit(request, "mcp.services.read", server, {"unit_name": unit_name})
        return Response(ServiceReadSerializer(service).data)


class AuditListView(ControlAPIView):
    permission_classes = [require_scope("audit:read")]

    def get(self, request):
        try:
            limit = max(1, min(int(request.query_params.get("limit", "20")), 100))
        except ValueError:
            return Response(
                {
                    "error": "invalid_request",
                    "message": "limit must be an integer.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = AuditEvent.objects.all()
        server_id = request.query_params.get("server_id")
        server = None
        if server_id:
            try:
                server = resolve_server(server_id)
            except ServerResolutionError as exc:
                return _error(exc)
            qs = qs.filter(target_type="server", target_id=str(server.public_id))
        items = list(qs[:limit])
        _audit(
            request,
            "mcp.audit.read",
            server,
            {"limit": limit, "count": len(items)},
        )
        return Response({"items": AuditReadSerializer(items, many=True).data})
