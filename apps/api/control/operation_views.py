from rest_framework import status
from rest_framework.response import Response

from control.authentication import ServicePrincipalAuthentication
from control.models import Operation
from control.operation_serializers import OperationCreateSerializer, serialize_operation
from control.permissions import require_scope
from control.services.operations import create_operation
from rest_framework.views import APIView


class OperationListCreateView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]

    def get_permissions(self):
        scope = "operations:create" if self.request.method == "POST" else "operations:read"
        return [require_scope(scope)()]

    def get(self, request):
        operations = Operation.objects.select_related("server")[:100]
        include_logs = "logs:read" in set(request.user.scopes)
        return Response(
            {
                "items": [
                    serialize_operation(
                        item,
                        include_result=include_logs
                        or item.kind != Operation.KIND_SERVICE_LOGS,
                    )
                    for item in operations
                ]
            }
        )

    def post(self, request):
        serializer = OperationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        server = data.pop("server")
        if server.status != "online":
            return Response(
                {"error": "server_offline", "message": "Server is not online."},
                status=status.HTTP_409_CONFLICT,
            )
        data.pop("server_id", None)
        operation = create_operation(server=server, actor=request.user.name, **data)
        return Response(
            serialize_operation(operation, include_result=True),
            status=status.HTTP_201_CREATED,
        )


class OperationDetailView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:read")]

    def get(self, request, operation_id):
        try:
            operation = Operation.objects.select_related("server").get(
                public_id=operation_id
            )
        except Operation.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        include_result = (
            operation.kind != Operation.KIND_SERVICE_LOGS
            or "logs:read" in set(request.user.scopes)
        )
        return Response(serialize_operation(operation, include_result=include_result))
