from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from control.agent_serializers import (
    EnrollRequestSerializer,
    HeartbeatRequestSerializer,
    OperationCompleteSerializer,
    OperationStartedSerializer,
)
from control.operation_serializers import serialize_operation
from control.models import DatabaseResource, Operation
from control.services.operations import (
    OperationTransitionError,
    claim_next_operation,
    complete_operation,
    start_operation,
)
from control.services.secrets import decrypt_secret
from control.authentication import AgentTokenAuthentication
from control.services.enrollment import EnrollmentError, enroll_agent
from control.services.heartbeat import apply_heartbeat


def _bearer(request) -> str:
    raw = request.headers.get("Authorization", "")
    if not raw.startswith("Bearer "):
        return ""
    return raw[7:].strip()


class EnrollView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EnrollRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = enroll_agent(
                enrollment_secret=_bearer(request),
                **serializer.validated_data,
            )
        except EnrollmentError:
            return Response(
                {"detail": "Invalid enrollment credential"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(
            {
                "server_id": str(result.server.public_id),
                "agent_token": result.agent_token,
            },
            status=status.HTTP_201_CREATED,
        )


class HeartbeatView(APIView):
    authentication_classes = [AgentTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = HeartbeatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        apply_heartbeat(request.user.server, serializer.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AgentOperationView(APIView):
    authentication_classes = [AgentTokenAuthentication]
    permission_classes = [IsAuthenticated]


class OperationClaimView(AgentOperationView):
    def post(self, request):
        claimed = claim_next_operation(server=request.user.server)
        if claimed is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        operation_data = serialize_operation(claimed.operation, include_result=False)
        if claimed.operation.kind in {
            Operation.KIND_DATABASE_CREATE,
            Operation.KIND_DATABASE_RESTORE,
        }:
            database = DatabaseResource.objects.get(
                public_id=claimed.operation.payload["database_resource_id"],
                server=request.user.server,
            )
            operation_data["execution"] = {
                "database_name": database.database_name,
                "username": database.username,
            }
            if claimed.operation.kind == Operation.KIND_DATABASE_CREATE:
                operation_data["execution"]["password"] = decrypt_secret(
                    database.password_ciphertext
                )
            else:
                operation_data["execution"]["backup_name"] = claimed.operation.payload[
                    "backup_name"
                ]
        return Response({"operation": operation_data, "claim_token": claimed.claim_token})


class OperationStartedView(AgentOperationView):
    def post(self, request, operation_id):
        serializer = OperationStartedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            operation = start_operation(
                operation_id=operation_id,
                server=request.user.server,
                **serializer.validated_data,
            )
        except OperationTransitionError as exc:
            return Response(
                {"error": "operation_transition_rejected", "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(serialize_operation(operation, include_result=False))


class OperationCompleteView(AgentOperationView):
    def post(self, request, operation_id):
        serializer = OperationCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            operation = complete_operation(
                operation_id=operation_id,
                server=request.user.server,
                **serializer.validated_data,
            )
        except OperationTransitionError as exc:
            return Response(
                {"error": "operation_transition_rejected", "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(serialize_operation(operation, include_result=False))
