"""Fail-closed management policy and secret-free response projection."""
import json
import re
from urllib.parse import urlsplit

from django.conf import settings
from rest_framework.exceptions import PermissionDenied

from control.coolify_client import CoolifyUpstreamError
from control.coolify_serializers import IDENTIFIER, protected_name
from control.models import CoolifyManagedApplication

# Exact upstream-generated messages only. Arbitrary build output never escapes.
SAFE_LOG_MESSAGES = frozenset({
    "New container started.", "New container is healthy.", "New container is unhealthy.",
    "Building docker image with Railpack.", "Building docker image started.",
    "Building docker image completed.",
    "New container is not healthy, rolling back to the old container.",
    "Deployment failed. Removing the new version of your application.",
})
DEPLOYMENT_STATES = {"queued", "in_progress", "finished", "failed", "cancelled-by-user"}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(IDENTIFIER, value):
        raise CoolifyUpstreamError("Invalid Coolify response.")
    return value


def target_policy(request, target):
    policy = settings.COOLIFY_MANAGEMENT_TARGETS.get(target)
    if not isinstance(policy, dict) or request.user.name not in policy.get("principals", []):
        raise PermissionDenied("Coolify target is not authorized.")
    return policy


def managed_application(request, application_uuid):
    row = CoolifyManagedApplication.objects.filter(
        application_uuid=application_uuid, principal=request.user.principal, deleted=False,
    ).first()
    if row is None:
        raise PermissionDenied("Application is not managed by this identity.")
    return row, target_policy(request, row.target)


def check_settings(policy, data):
    if "git_repository" in data and data["git_repository"] not in policy.get("repositories", []):
        raise PermissionDenied("Repository is not authorized.")
    if any(domain not in policy.get("domains", []) for domain in data.get("domains", [])):
        raise PermissionDenied("Domain is not authorized.")


def checked_application(client, application_uuid, policy):
    app = client.get_application(application_uuid)
    if not isinstance(app, dict) or app.get("uuid") != application_uuid:
        raise CoolifyUpstreamError("Invalid Coolify response.")
    if not isinstance(app.get("name"), str) or not app["name"]:
        raise CoolifyUpstreamError("Invalid Coolify application name.")
    if protected_name(app["name"]):
        raise PermissionDenied("Protected application.")
    # Refuse drift to unreviewed code, including changes made in the Coolify UI.
    approved_repositories = set(policy.get("repositories", []))
    # Coolify stores GitHub URLs as owner/repo (public and private GitHub App).
    # Only derive slugs from explicitly approved GitHub URLs, never other hosts.
    for repository in policy.get("repositories", []):
        url = urlsplit(repository)
        if url.hostname == "github.com":
            slug = url.path.strip("/")
            approved_repositories.update({slug, slug.removesuffix(".git")})
    repository = app.get("git_repository")
    if not isinstance(repository, str) or repository not in approved_repositories:
        raise PermissionDenied("Repository is not authorized.")
    environment = client.get_environment(policy["project_uuid"], policy["environment_uuid"])
    resources = client.list_server_resources(policy["server_uuid"])
    if not isinstance(environment, dict) or not isinstance(environment.get("applications"), list) or not isinstance(resources, list):
        raise CoolifyUpstreamError("Invalid Coolify placement response.")
    if not any(isinstance(item, dict) and item.get("uuid") == application_uuid for item in environment["applications"]):
        raise PermissionDenied("Application placement has changed.")
    if not any(isinstance(item, dict) and item.get("uuid") == application_uuid for item in resources):
        raise PermissionDenied("Application server has changed.")
    return app


def settings_payload(data):
    payload = dict(data)
    for key in ("ports_exposes", "domains"):
        if key in payload:
            payload[key] = ",".join(str(value) for value in payload[key])
    if "limits_cpus" in payload:
        payload["limits_cpus"] = str(payload["limits_cpus"])
    return payload


def deployment_summary(data):
    if not isinstance(data, dict):
        raise CoolifyUpstreamError("Invalid Coolify response.")
    state = data.get("status")
    return {
        "deployment_uuid": identifier(data.get("deployment_uuid")),
        "status": state if isinstance(state, str) and state in DEPLOYMENT_STATES else "unknown",
    }


def deployment_logs(data, lines):
    # Arbitrary build output can contain secrets unrelated to application envs
    # (shared/server/build credentials). Regex-only scrubbing cannot guarantee
    # confidentiality. Preserve bounded structure and exact approved constants;
    # suppress all other free text.
    raw = data.get("logs")
    if raw is None:
        return {"items": [], "available": False, "redaction": "allowlisted_messages"}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = [raw]
    if not isinstance(raw, list):
        raise CoolifyUpstreamError("Invalid Coolify log response.")
    return {
        "items": [{"output": safe_log_output(item)} for item in raw[-lines:]],
        "available": True, "truncated": len(raw) > lines, "redaction": "allowlisted_messages",
    }


def safe_log_output(item):
    output = item.get("output") if isinstance(item, dict) else None
    return output if isinstance(output, str) and output in SAFE_LOG_MESSAGES else "[REDACTED]"
