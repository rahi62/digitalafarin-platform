from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from control.models import AgentCredential, AuditEvent, EnrollmentToken, Server
from control.security import issue_secret, parse_secret, verify_secret


class EnrollmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnrollmentResult:
    server: Server
    agent_token: str


@transaction.atomic
def enroll_agent(
    *,
    enrollment_secret: str,
    name: str,
    hostname: str,
    agent_version: str,
    capabilities: list[str],
) -> EnrollmentResult:
    try:
        prefix, secret = parse_secret(enrollment_secret, "enroll")
        token = EnrollmentToken.objects.select_for_update().get(token_prefix=prefix)
    except (ValueError, EnrollmentToken.DoesNotExist) as exc:
        raise EnrollmentError("invalid enrollment credential") from exc

    now = timezone.now()
    if (
        token.used_at is not None
        or token.expires_at <= now
        or not verify_secret(secret, token.secret_hash)
    ):
        raise EnrollmentError("invalid enrollment credential")

    server = Server.objects.create(
        name=name,
        hostname=hostname,
        agent_version=agent_version,
        capabilities=capabilities,
    )
    issued = issue_secret("agent")
    AgentCredential.objects.create(
        server=server,
        token_prefix=issued.prefix,
        token_hash=issued.digest,
    )
    token.used_at = now
    token.save(update_fields=["used_at"])
    AuditEvent.objects.create(
        event_type="agent.enrolled",
        target_type="server",
        target_id=str(server.public_id),
        actor="enrollment",
        metadata={"hostname": hostname},
    )
    return EnrollmentResult(server=server, agent_token=issued.cleartext)
