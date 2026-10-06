"""Explicit Control Plane operations; no caller-selected upstream paths/methods."""
from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import ParseError, PermissionDenied, UnsupportedMediaType
from rest_framework.response import Response

from control.control_views import ControlAPIView, _audit
from control.coolify_client import CoolifyClient, CoolifyConfigurationError, CoolifyUpstreamError
from control.coolify_management import (
    checked_application, check_settings, deployment_logs, deployment_summary,
    identifier, managed_application, settings_payload, target_policy,
)
from control.coolify_serializers import (
    ApplicationCreateSerializer, ApplicationSettingsSerializer, DeleteSerializer,
    EmptySerializer, EnvironmentWriteSerializer, LogQuerySerializer,
)
from control.models import CoolifyManagedApplication
from control.permissions import require_scope


class ManagementView(ControlAPIView):
    permission_classes = [require_scope("coolify:manage")]
    serializer_class = EmptySerializer
    action = ""

    def permission_denied(self, request, message=None, code=None):
        if getattr(request.user, "name", None):
            _audit(request, "mcp.coolify.authorization.denied", metadata={"action": self.action})
        return super().permission_denied(request, message, code)

    def execute(self, request, callback, application_uuid=None):
        # Audit records never contain payloads, env keys/values, upstream text,
        # exception strings, repository credentials, or logs.
        metadata = {"action": self.action}
        if application_uuid:
            metadata["application_uuid"] = application_uuid
        _audit(request, "mcp.coolify.requested", metadata=metadata)
        try:
            source = request.query_params if request.method == "GET" else request.data
            serializer = self.serializer_class(data=source)
            serializer.is_valid(raise_exception=True)
            client = CoolifyClient()
            try:
                result = callback(client, serializer.validated_data)
            finally:
                client.close()
        except (serializers.ValidationError, ParseError, UnsupportedMediaType):
            response = Response({"error": "invalid_request", "message": "Invalid Coolify request."}, status=400)
        except PermissionDenied:
            response = Response({"error": "forbidden", "message": "Coolify operation is not authorized."}, status=403)
        except CoolifyConfigurationError:
            response = Response({"error": "coolify_not_configured", "message": "Coolify integration is not configured."}, status=503)
        except CoolifyUpstreamError:
            response = Response({"error": "coolify_unavailable", "message": "Coolify request failed; reconcile state before retrying a write."}, status=502)
        else:
            response = Response(result)
        _audit(request, "mcp.coolify.completed", metadata={**metadata, "http_status": response.status_code})
        return response


class CoolifyEnvironmentListView(ManagementView):
    permission_classes = [require_scope("coolify:read")]
    action = "environments.read"

    def get(self, request, project_uuid):
        def call(client, data):
            items = client.list_environments(project_uuid)
            if not isinstance(items, list):
                raise CoolifyUpstreamError()
            # Names/descriptions may hold arbitrary sensitive text; UUIDs suffice
            # for target configuration and environment selection.
            return {"items": [{"uuid": identifier(item.get("uuid"))} for item in items[:200] if isinstance(item, dict)]}
        return self.execute(request, call)


class CoolifyApplicationCreateView(ManagementView):
    serializer_class = ApplicationCreateSerializer
    action = "application.create"

    def post(self, request):
        def call(client, data):
            policy = target_policy(request, data["target"])
            check_settings(policy, data)
            placement = {key: identifier(policy.get(key)) for key in ("project_uuid", "environment_uuid", "server_uuid")}
            if policy.get("destination_uuid"):
                placement["destination_uuid"] = identifier(policy["destination_uuid"])
            try:
                with transaction.atomic():
                    row = CoolifyManagedApplication.objects.create(
                        request_id=data["request_id"], target=data["target"], principal=request.user.principal,
                    )
            except IntegrityError:
                raise serializers.ValidationError("Request already submitted; reconcile before retrying.") from None
            payload = settings_payload({key: value for key, value in data.items() if key not in {"target", "request_id"}})
            payload.update(placement)
            payload.update(instant_deploy=False, autogenerate_domain=False,
                           is_auto_deploy_enabled=False, is_preview_deployments_enabled=False)
            if policy.get("github_app_uuid"):
                payload["github_app_uuid"] = identifier(policy["github_app_uuid"])
                result = client.create_github_application(payload)
            else:
                result = client.create_application(payload)
            if not isinstance(result, dict):
                raise CoolifyUpstreamError()
            row.application_uuid = identifier(result.get("uuid"))
            try:
                with transaction.atomic():
                    row.save(update_fields=["application_uuid"])
            except IntegrityError:
                raise CoolifyUpstreamError() from None
            _audit(request, "mcp.coolify.application.registered", metadata={"application_uuid": row.application_uuid, "request_id": str(row.request_id)})
            return {"application_uuid": row.application_uuid}
        return self.execute(request, call)


class CoolifyApplicationUpdateView(ManagementView):
    serializer_class = ApplicationSettingsSerializer
    action = "application.update"

    def post(self, request, application_uuid):
        def call(client, data):
            if not data:
                raise serializers.ValidationError("Empty update.")
            _, policy = managed_application(request, application_uuid)
            check_settings(policy, data)
            checked_application(client, application_uuid, policy)
            client.update_application(application_uuid, settings_payload(data))
            return {"application_uuid": application_uuid, "updated": True}
        return self.execute(request, call, application_uuid)


class CoolifyEnvironmentVariablesView(ManagementView):
    permission_classes = [require_scope("coolify:read")]
    action = "environment.read"

    def get(self, request, application_uuid):
        def call(client, data):
            _, policy = managed_application(request, application_uuid)
            checked_application(client, application_uuid, policy)
            values = client.list_environment_variables(application_uuid)
            if not isinstance(values, list):
                raise CoolifyUpstreamError()
            # Only administrator-approved keys; never serialize upstream values,
            # comments, nested objects, or unrecognized fields.
            return {"items": [
                {"key": item["key"], "is_buildtime": item.get("is_buildtime") is True,
                 "is_runtime": item.get("is_runtime") is True}
                for item in values[:200] if isinstance(item, dict) and item.get("key") in policy.get("environment_keys", [])
            ]}
        return self.execute(request, call, application_uuid)


class CoolifyEnvironmentCreateView(ManagementView):
    serializer_class = EnvironmentWriteSerializer
    action = "environment.create"
    update = False

    def post(self, request, application_uuid):
        def call(client, data):
            _, policy = managed_application(request, application_uuid)
            if data["key"] not in policy.get("environment_keys", []):
                raise PermissionDenied()
            checked_application(client, application_uuid, policy)
            payload = {**data, "is_literal": True, "is_preview": False, "is_multiline": "\n" in data["value"], "is_shown_once": True}
            method = client.update_environment_variable if self.update else client.create_environment_variable
            method(application_uuid, payload)
            return {"application_uuid": application_uuid, "updated": True}
        return self.execute(request, call, application_uuid)


class CoolifyEnvironmentUpdateView(CoolifyEnvironmentCreateView):
    action = "environment.update"
    update = True


class CoolifyApplicationActionView(ManagementView):
    permission_classes = [require_scope("coolify:deploy")]
    action = "deploy"

    def post(self, request, application_uuid):
        def call(client, data):
            _, policy = managed_application(request, application_uuid)
            checked_application(client, application_uuid, policy)
            calls = {
                "deploy": lambda: client.deploy_application(application_uuid),
                "redeploy": lambda: client.deploy_application(application_uuid, force=True),
                "start": lambda: client.start_application(application_uuid),
                "stop": lambda: client.stop_application(application_uuid),
                "restart": lambda: client.restart_application(application_uuid),
            }
            result = calls[self.action]()
            if not isinstance(result, dict):
                raise CoolifyUpstreamError()
            response = {"application_uuid": application_uuid, "action": self.action}
            if result.get("deployment_uuid"):
                response.update(deployment_uuid=identifier(result["deployment_uuid"]), queued=True)
            else:
                response["queued"] = self.action == "stop"
            return response
        return self.execute(request, call, application_uuid)


class CoolifyApplicationDeleteView(ManagementView):
    permission_classes = [require_scope("coolify:delete")]
    serializer_class = DeleteSerializer
    action = "application.delete"

    def post(self, request, application_uuid):
        def call(client, data):
            if data["confirm_application_uuid"] != application_uuid:
                raise serializers.ValidationError("Exact application confirmation required.")
            row, policy = managed_application(request, application_uuid)
            checked_application(client, application_uuid, policy)
            client.delete_application(application_uuid)
            row.deleted = True
            row.save(update_fields=["deleted"])
            return {"application_uuid": application_uuid, "deletion_queued": True, "volumes_preserved": True}
        return self.execute(request, call, application_uuid)


class CoolifyDeploymentListView(ManagementView):
    permission_classes = [require_scope("coolify:read")]
    action = "deployments.read"

    def get(self, request, application_uuid):
        def call(client, data):
            _, policy = managed_application(request, application_uuid)
            checked_application(client, application_uuid, policy)
            result = client.list_application_deployments(application_uuid)
            if not isinstance(result, dict) or not isinstance(result.get("deployments"), list):
                raise CoolifyUpstreamError()
            return {"items": [deployment_summary(item) for item in result["deployments"][:20]]}
        return self.execute(request, call, application_uuid)


class CoolifyDeploymentDetailView(ManagementView):
    permission_classes = [require_scope("coolify:read")]
    action = "deployment.read"
    logs = False

    def get(self, request, application_uuid, deployment_uuid):
        def call(client, data):
            _, policy = managed_application(request, application_uuid)
            checked_application(client, application_uuid, policy)
            # 4.3.23 intentionally hides Application.id. Derive the owning ID
            # from the application-scoped deployment list, never caller input.
            scoped = client.list_application_deployments(application_uuid)
            if not isinstance(scoped, dict) or not isinstance(scoped.get("deployments"), list):
                raise CoolifyUpstreamError()
            rows = scoped["deployments"]
            if not rows or not isinstance(rows[0], dict):
                raise PermissionDenied()
            owner_id = rows[0].get("application_id")
            if not str(owner_id).isdigit():
                raise CoolifyUpstreamError()
            deployment = client.get_deployment(deployment_uuid)
            if not isinstance(deployment, dict) or deployment.get("deployment_uuid") != deployment_uuid:
                raise CoolifyUpstreamError()
            if str(deployment.get("application_id")) != str(owner_id):
                raise PermissionDenied()
            result = deployment_summary(deployment)
            if self.logs:
                result.update(deployment_logs(deployment, data["lines"]))
            return result
        return self.execute(request, call, application_uuid)


class CoolifyDeploymentLogsView(CoolifyDeploymentDetailView):
    serializer_class = LogQuerySerializer
    action = "deployment.logs.read"
    logs = True


class CoolifyManagementTargetListView(ControlAPIView):
    permission_classes = [require_scope("coolify:read")]

    def get(self, request):
        items = []
        for name, policy in settings.COOLIFY_MANAGEMENT_TARGETS.items():
            if request.user.name in policy.get("principals", []):
                items.append({"target": name, **{key: policy[key] for key in (
                    "project_uuid", "environment_uuid", "server_uuid", "destination_uuid",
                    "repositories", "domains", "environment_keys",
                ) if key in policy}})
        _audit(request, "mcp.coolify.targets.read")
        return Response({"items": items[:100]})
