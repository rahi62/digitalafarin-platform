from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.models import Service, ServiceTakeover
from control.permissions import require_scope
from control.services.takeovers import (
    TakeoverError,
    cancel_prepared_takeover,
    queue_takeover_activation,
    queue_takeover_prepare,
)
from control.takeover_serializers import ServiceTakeoverSerializer, TakeoverPrepareSerializer


def _takeover_error(exc: TakeoverError):
    return Response(
        {"error": exc.code, "message": str(exc)},
        status=status.HTTP_409_CONFLICT,
    )


def _get_takeover(takeover_id):
    try:
        return ServiceTakeover.objects.select_related(
            "service", "service__project", "prepare_operation", "activate_operation"
        ).get(public_id=takeover_id)
    except ServiceTakeover.DoesNotExist:
        return None


class ServiceTakeoverListCreateView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]

    def get_permissions(self):
        scope = "operations:create" if self.request.method == "POST" else "operations:read"
        return [require_scope(scope)()]

    def _service(self, service_id):
        try:
            return Service.objects.select_related("project", "target_server").get(
                public_id=service_id
            )
        except Service.DoesNotExist:
            return None

    def get(self, request, service_id):
        service = self._service(service_id)
        if service is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        rows = service.takeovers.select_related(
            "service", "prepare_operation", "activate_operation"
        ).all()
        return Response({"items": ServiceTakeoverSerializer(rows, many=True).data})

    def post(self, request, service_id):
        service = self._service(service_id)
        if service is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = TakeoverPrepareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            takeover, _operation = queue_takeover_prepare(
                service=service,
                exact_commit=serializer.validated_data["commit"],
                requested_by=request.user.name,
            )
        except TakeoverError as exc:
            return _takeover_error(exc)
        return Response(
            ServiceTakeoverSerializer(takeover).data,
            status=status.HTTP_201_CREATED,
        )


class TakeoverDetailView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:read")]

    def get(self, request, takeover_id):
        takeover = _get_takeover(takeover_id)
        if takeover is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(ServiceTakeoverSerializer(takeover).data)


class TakeoverActivateView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def post(self, request, takeover_id):
        if request.data not in ({}, None):
            return Response(
                {"error": "invalid_request", "message": "Activation body must be empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        takeover = _get_takeover(takeover_id)
        if takeover is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            queue_takeover_activation(
                takeover=takeover,
                requested_by=request.user.name,
            )
        except TakeoverError as exc:
            return _takeover_error(exc)
        takeover = _get_takeover(takeover_id)
        return Response(
            ServiceTakeoverSerializer(takeover).data,
            status=status.HTTP_202_ACCEPTED,
        )


class TakeoverCancelView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def post(self, request, takeover_id):
        if request.data not in ({}, None):
            return Response(
                {"error": "invalid_request", "message": "Cancel body must be empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        takeover = _get_takeover(takeover_id)
        if takeover is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            takeover = cancel_prepared_takeover(
                takeover=takeover,
                actor=request.user.name,
            )
        except TakeoverError as exc:
            return _takeover_error(exc)
        return Response(ServiceTakeoverSerializer(takeover).data)
