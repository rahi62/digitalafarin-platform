from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from control.models import AgentCredential, AuditEvent, Server


class Command(BaseCommand):
    help = "Revoke all active agent credentials for one server UUID."

    def add_arguments(self, parser):
        parser.add_argument("server_id")
        parser.add_argument("--actor", default="operator")

    def handle(self, *args, **options):
        try:
            server = Server.objects.get(public_id=options["server_id"])
        except (ValueError, Server.DoesNotExist) as exc:
            raise CommandError("server not found") from exc
        now = timezone.now()
        count = AgentCredential.objects.filter(
            server=server,
            revoked_at__isnull=True,
        ).update(revoked_at=now)
        AuditEvent.objects.create(
            event_type="agent.credential.revoked",
            target_type="server",
            target_id=str(server.public_id),
            actor=options["actor"],
            metadata={"credential_count": count},
        )
        self.stdout.write(str(count))
