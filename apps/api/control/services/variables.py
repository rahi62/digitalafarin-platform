from control.models import EnvironmentVariable, Service
from control.services.secrets import decrypt_secret


def resolve_environment(
    service: Service,
    environment: str,
    *,
    include_secrets: bool,
    target: str | None = None,
) -> dict[str, str]:
    variables = EnvironmentVariable.objects.filter(project=service.project).order_by("created_at")
    resolved = {}
    for scope in (
        EnvironmentVariable.SCOPE_PROJECT,
        EnvironmentVariable.SCOPE_SERVICE,
        EnvironmentVariable.SCOPE_ENVIRONMENT,
    ):
        for variable in variables.filter(scope=scope):
            if target and variable.target not in {target, EnvironmentVariable.TARGET_BOTH}:
                continue
            if scope != EnvironmentVariable.SCOPE_PROJECT and variable.service_id != service.id:
                continue
            if scope == EnvironmentVariable.SCOPE_ENVIRONMENT and variable.environment != environment:
                continue
            if variable.value_type == EnvironmentVariable.TYPE_SECRET:
                if include_secrets:
                    resolved[variable.key] = decrypt_secret(variable.secret_ciphertext)
            else:
                resolved[variable.key] = variable.plain_value
    return resolved
