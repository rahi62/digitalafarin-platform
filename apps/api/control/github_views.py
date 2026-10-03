import hashlib
import hmac
import json
import os

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from control.authentication import ServicePrincipalAuthentication
from control.models import GitHubDelivery, GitHubInstallation, Service
from control.permissions import require_scope
from control.services.github_source import GitHubSourceError, installation_details, installation_repositories
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


class GitHubIntegrationView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:read")]

    def get(self, request):
        slug = os.getenv("GITHUB_APP_SLUG", "").strip()
        configured = bool(
            os.getenv("GITHUB_APP_ID", "").strip()
            and os.getenv("GITHUB_APP_PRIVATE_KEY", "").strip()
            and os.getenv("GITHUB_APP_WEBHOOK_SECRET", "").strip()
            and slug
        )
        return Response({
            "configured": configured,
            "app_slug": slug if configured else "",
            "install_url": f"https://github.com/apps/{slug}/installations/new" if configured else "",
            "installations": [
                {
                    "installation_id": item.installation_id,
                    "account_login": item.account_login,
                    "account_type": item.account_type,
                    "repository_selection": item.repository_selection,
                    "suspended": item.suspended,
                }
                for item in GitHubInstallation.objects.all()
            ],
        })


class GitHubInstallationView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:create")]

    def post(self, request):
        if set(request.data) != {"installation_id"}:
            return Response({"error": "invalid_request"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            installation_id = int(request.data["installation_id"])
            if installation_id <= 0:
                raise ValueError
            details = installation_details(installation_id)
        except (TypeError, ValueError, GitHubSourceError):
            return Response(
                {"error": "github_installation_unavailable"},
                status=status.HTTP_409_CONFLICT,
            )
        record, _ = GitHubInstallation.objects.update_or_create(
            installation_id=installation_id,
            defaults={
                "account_login": details["account_login"],
                "account_type": details["account_type"],
                "repository_selection": details["repository_selection"],
                "suspended": details["suspended"],
            },
        )
        return Response({
            "installation_id": record.installation_id,
            "account_login": record.account_login,
            "account_type": record.account_type,
            "repository_selection": record.repository_selection,
            "suspended": record.suspended,
        })


class GitHubRepositoryListView(APIView):
    authentication_classes = [ServicePrincipalAuthentication]
    permission_classes = [require_scope("operations:read")]

    def get(self, request, installation_id):
        if not GitHubInstallation.objects.filter(installation_id=installation_id, suspended=False).exists():
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            items = installation_repositories(installation_id)
        except GitHubSourceError:
            return Response(
                {"error": "github_repositories_unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"items": items})
