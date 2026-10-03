import hashlib
import hmac
import json
import os

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from control.models import GitHubDelivery, Service
from control.services.deployments import DeploymentAdmissionError, queue_deployment


class GitHubWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        delivery_id = request.headers.get("X-GitHub-Delivery", "")
        event = request.headers.get("X-GitHub-Event", "")
        signature = request.headers.get("X-Hub-Signature-256", "")
        secret = os.getenv("GITHUB_APP_WEBHOOK_SECRET", "").strip()
        if not delivery_id or event != "push" or not signature.startswith("sha256=") or not secret:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature[7:], expected):
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            payload = json.loads(request.body)
            repository = payload["repository"]["html_url"].rstrip("/")
            branch = payload["ref"].removeprefix("refs/heads/")
            commit = payload["after"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        if len(commit) != 40:
            return Response(status=status.HTTP_202_ACCEPTED)
        services = list(Service.objects.filter(
            repository__in=[repository, repository + ".git"],
            branch=branch,
            auto_deploy=True,
            lifecycle_state=Service.LIFECYCLE_MANAGED,
        ).select_related("target_server"))
        deployments = []
        for service in services:
            try:
                with transaction.atomic():
                    delivery, created = GitHubDelivery.objects.get_or_create(
                        delivery_id=delivery_id,
                        service=service,
                        defaults={"event": event, "commit": commit},
                    )
                    if not created:
                        continue
                    deployment, _operation = queue_deployment(
                        service=service,
                        requested_ref=commit,
                        resolved_commit=commit,
                        requested_by="github-webhook",
                    )
                    deployments.append(str(deployment.public_id))
            except DeploymentAdmissionError:
                continue
            except IntegrityError:
                continue
        return Response({"deployment_ids": deployments}, status=status.HTTP_202_ACCEPTED)
