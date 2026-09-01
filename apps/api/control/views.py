from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AuditEvent, Server
from .serializers import AuditEventSerializer, ServerSerializer
from .services.agent_client import AgentClientError
from .services.sync import sync_server


class ServerViewSet(viewsets.ModelViewSet):
    queryset = Server.objects.prefetch_related("services").all().order_by("id")
    serializer_class = ServerSerializer

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        server = self.get_object()
        try:
            sync_server(server, actor=str(request.user))
        except AgentClientError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        server.refresh_from_db()
        return Response(self.get_serializer(server).data)


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditEvent.objects.all()[:100]
    serializer_class = AuditEventSerializer
