from django.db import transaction
from django.http import HttpResponse

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
from control.services.operations import (
    OperationTransitionError,
    claim_next_operation,
    complete_operation,
    start_operation,
)
from control.services.execution import build_execution_context
from control.models import Operation
from control.services.deployments import apply_deployment_result
from control.services.github_source import GitHubSourceError, download_archive
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
        except (OperationTransitionError, TakeoverError) as exc:
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
            operation_record = Operation.objects.get(
                public_id=operation_id, server=request.user.server
            )
            if operation_record.kind in {
                Operation.KIND_TAKEOVER_PREPARE,
                Operation.KIND_TAKEOVER_ACTIVATE,
            }:
                # Validate the claim and operation state before trusting any takeover result.
                # The outer transaction rolls the Operation completion back if takeover
                # result validation/finalization rejects the Agent response.
                with transaction.atomic():
                    operation = complete_operation(
                        operation_id=operation_id,
                        server=request.user.server,
                        **serializer.validated_data,
                    )
                    apply_takeover_result(
                        operation,
                        succeeded=serializer.validated_data["succeeded"],
                        result=serializer.validated_data.get("result", {}),
                        error_code=serializer.validated_data.get("error_code", ""),
                        error_message=serializer.validated_data.get("error_message", ""),
                    )
            else:
                if operation_record.kind in {
                    Operation.KIND_DEPLOYMENT_DEPLOY,
                    Operation.KIND_DEPLOYMENT_ROLLBACK,
                }:
                    apply_deployment_result(
                        operation_record,
                        succeeded=serializer.validated_data["succeeded"],
                        result=serializer.validated_data.get("result", {}),
                        error_code=serializer.validated_data.get("error_code", ""),
                    )
                operation = complete_operation(
                    operation_id=operation_id,
                    server=request.user.server,
                    **serializer.validated_data,
                )
        except (OperationTransitionError, TakeoverError) as exc:
            return Response(
                {"error": "operation_transition_rejected", "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(serialize_operation(operation, include_result=False))


class OperationSourceView(AgentOperationView):
    def get(self, request, operation_id):
        claim_token = request.headers.get("X-DigitalAfarin-Claim", "")
        try:
            operation = Operation.objects.select_related("server").get(
                public_id=operation_id,
                server=request.user.server,
                kind=Operation.KIND_DEPLOYMENT_DEPLOY,
                state=Operation.STATE_RUNNING,
            )
        except Operation.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not operation.claim_token or not claim_token or not __import__("secrets").compare_digest(operation.claim_token, claim_token):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            deployment = operation.server.managed_services.filter(
                deployments__public_id=operation.payload.get("deployment_id")
            ).select_related("project").prefetch_related("deployments").first()
            if deployment is None:
                return Response(status=status.HTTP_404_NOT_FOUND)
            record = deployment.deployments.get(public_id=operation.payload["deployment_id"])
            data = download_archive(deployment.repository, record.resolved_commit)
        except (GitHubSourceError, KeyError):
            return Response({"error": "source_unavailable"}, status=status.HTTP_502_BAD_GATEWAY)
        response = HttpResponse(data, content_type="application/gzip")
        response["Content-Disposition"] = 'attachment; filename="source.tar.gz"'
        response["X-DigitalAfarin-Commit"] = record.resolved_commit
        return response
