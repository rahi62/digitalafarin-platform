from django.db import transaction

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from control.agent_serializers import (
    EnrollRequestSerializer,
    HeartbeatRequestSerializer,
    OperationCompleteSerializer,
    OperationStartedSerializer,
    OperationProgressSerializer,
)
from control.operation_serializers import serialize_operation
from control.services.operations import (
    OperationTransitionError,
    claim_next_operation,
    complete_operation,
    start_operation,
    report_progress,
)
from control.services.execution import build_execution_context
from control.services.provisioning import apply_provisioning_result
from control.models import Operation, Service
from control.services.deployments import DeploymentTransitionError, apply_deployment_result
from control.services.takeovers import (
    TakeoverError,
    apply_takeover_result,
    mark_takeover_operation_started,
)
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
        execution = build_execution_context(claimed.operation)
        if execution is not None:
            operation_data["execution"] = execution
        return Response({"operation": operation_data, "claim_token": claimed.claim_token})


class OperationStartedView(AgentOperationView):
    def post(self, request, operation_id):
        serializer = OperationStartedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                operation = start_operation(
                    operation_id=operation_id,
                    server=request.user.server,
                    **serializer.validated_data,
                )
                mark_takeover_operation_started(operation)
                if operation.kind == Operation.KIND_SERVICE_PROVISION:
                    Service.objects.filter(
                        pk=operation.serviceprovisioning.service_id, lifecycle_state='pending'
                    ).update(lifecycle_state='provisioning')
        except (OperationTransitionError, TakeoverError) as exc:
            return Response(
                {"error": "operation_transition_rejected", "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(serialize_operation(operation, include_result=False))


class OperationProgressView(AgentOperationView):
    def post(self, request, operation_id):
        serializer = OperationProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            operation = report_progress(operation_id=operation_id, server=request.user.server, **serializer.validated_data)
        except OperationTransitionError as exc:
            return Response({'error': 'operation_transition_rejected', 'message': str(exc)}, status=409)
        return Response(serialize_operation(operation, include_result=False))


class OperationCompleteView(AgentOperationView):
    def post(self, request, operation_id):
        serializer = OperationCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                operation_record = Operation.objects.select_for_update().get(
                    public_id=operation_id, server=request.user.server
                )
                already_complete = operation_record.state in {
                    Operation.STATE_SUCCEEDED, Operation.STATE_FAILED,
                }
                # Validate ownership/claim before ANY domain mutation. Failure in the
                # result application rolls back the operation and domain together.
                operation = complete_operation(
                    operation_id=operation_id,
                    server=request.user.server,
                    **serializer.validated_data,
                )
                if already_complete:
                    return Response(serialize_operation(operation, include_result=False))
                if operation.kind in {
                    Operation.KIND_TAKEOVER_PREPARE,
                    Operation.KIND_TAKEOVER_ACTIVATE,
                }:
                    apply_takeover_result(
                        operation,
                        succeeded=serializer.validated_data["succeeded"],
                        result=serializer.validated_data.get("result", {}),
                        error_code=serializer.validated_data.get("error_code", ""),
                        error_message=serializer.validated_data.get("error_message", ""),
                    )
                elif operation.kind == Operation.KIND_SERVICE_PROVISION:
                    apply_provisioning_result(operation, succeeded=serializer.validated_data['succeeded'],
                                              result=serializer.validated_data.get('result', {}),
                                              error_code=serializer.validated_data.get('error_code', ''))
                elif operation.kind in {
                    Operation.KIND_DEPLOYMENT_DEPLOY,
                    Operation.KIND_DEPLOYMENT_ROLLBACK,
                }:
                    apply_deployment_result(
                        operation,
                        succeeded=serializer.validated_data["succeeded"],
                        result=serializer.validated_data.get("result", {}),
                        error_code=serializer.validated_data.get("error_code", ""),
                    )
        except Operation.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        except (OperationTransitionError, TakeoverError, DeploymentTransitionError) as exc:
            return Response(
                {"error": "operation_transition_rejected", "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(serialize_operation(operation, include_result=False))
