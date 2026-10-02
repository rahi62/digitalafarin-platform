from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.models import Project, Service
from control.permissions import require_scope
from control.provisioning_serializers import ProvisionServiceSerializer
from control.services.deployments import DeploymentAdmissionError
from control.services.provisioning import queue_provisioning, serialize_provisioning, retry_provisioning


class ProvisionServiceView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope('operations:create')]

    def post(self, request, project_id):
        project = get_object_or_404(Project, public_id=project_id)
        key = request.headers.get('Idempotency-Key', '')
        if not key or len(key) > 120:
            return Response({'error': 'idempotency_key_required'}, status=400)
        serializer = ProvisionServiceSerializer(data=request.data, context={'project': project})
        serializer.is_valid(raise_exception=True)
        try:
            record = queue_provisioning(project=project, configuration=serializer.validated_data,
                                        actor=request.user.name, idempotency_key=key)
        except DeploymentAdmissionError as exc:
            return Response({'error': exc.code, 'message': str(exc)}, status=409)
        except IntegrityError:
            return Response({'error': 'service_conflict', 'message': 'A service with this identity already exists.'}, status=409)
        return Response(serialize_provisioning(record), status=202)


class RetryProvisionServiceView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope('operations:create')]

    def post(self, request, service_id):
        service = get_object_or_404(Service, public_id=service_id)
        key = request.headers.get('Idempotency-Key', '')
        if request.data or not key or len(key) > 120:
            return Response({'error': 'invalid_retry_request'}, status=400)
        try:
            record = retry_provisioning(service=service, actor=request.user.name, idempotency_key=key)
        except DeploymentAdmissionError as exc:
            return Response({'error': exc.code, 'message': str(exc)}, status=409)
        except IntegrityError:
            return Response({'error': 'idempotency_conflict'}, status=409)
        return Response(serialize_provisioning(record), status=202)
