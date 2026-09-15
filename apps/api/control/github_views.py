import hashlib
import hmac
import json

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from control.models import EnvironmentVariable, GitHubDelivery, Service
from control.services.deployments import DeploymentAdmissionError, queue_deployment
from control.services.secrets import decrypt_secret


class GitHubWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        delivery_id = request.headers.get("X-GitHub-Delivery", "")
        event = request.headers.get("X-GitHub-Event", "")
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not delivery_id or event != "push" or not signature.startswith("sha256="):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = json.loads(request.body)
            repository = payload["repository"]["html_url"].rstrip("/")
            branch = payload["ref"].removeprefix("refs/heads/")
            commit = payload["after"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        service = Service.objects.filter(repository__in=[repository, repository + ".git"], branch=branch).first()
        if service is None or len(commit) != 40:
            return Response(status=status.HTTP_202_ACCEPTED)
        variable = EnvironmentVariable.objects.filter(
            project=service.project,
            service=service,
            scope=EnvironmentVariable.SCOPE_SERVICE,
            key="GITHUB_WEBHOOK_SECRET",
            value_type=EnvironmentVariable.TYPE_SECRET,
        ).first()
        if variable is None:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        expected = hmac.new(decrypt_secret(variable.secret_ciphertext).encode(), request.body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature[7:], expected):
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        if GitHubDelivery.objects.filter(delivery_id=delivery_id).exists():
            return Response({"duplicate": True})
        try:
            with transaction.atomic():
                GitHubDelivery.objects.create(delivery_id=delivery_id, service=service, event=event, commit=commit)
                deployment, _operation = queue_deployment(
                    service=service,
                    requested_ref=commit,
                    resolved_commit=commit,
                    requested_by="github-webhook",
                )
        except DeploymentAdmissionError:
            return Response(status=status.HTTP_409_CONFLICT)
        except IntegrityError:
            return Response({"duplicate": True})
        return Response({"deployment_id": str(deployment.public_id)}, status=status.HTTP_202_ACCEPTED)
