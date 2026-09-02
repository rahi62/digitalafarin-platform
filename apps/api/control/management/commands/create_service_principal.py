from django.core.management.base import BaseCommand, CommandError

from control.models import ServiceCredential, ServicePrincipal
from control.security import issue_secret

READ_SCOPES = ["servers:read", "metrics:read", "services:read", "audit:read"]


class Command(BaseCommand):
    help = "Create or reactivate a read-only service principal credential."

    def add_arguments(self, parser):
        parser.add_argument("name")

    def handle(self, *args, **options):
        principal, created = ServicePrincipal.objects.get_or_create(
            name=options["name"],
            defaults={"scopes": READ_SCOPES},
        )
        if not created and principal.credentials.filter(revoked_at__isnull=True).exists():
            raise CommandError("principal already has an active credential")
        principal.scopes = READ_SCOPES
        principal.is_active = True
        principal.save(update_fields=["scopes", "is_active"])
        issued = issue_secret("service")
        ServiceCredential.objects.create(
            principal=principal,
            token_prefix=issued.prefix,
            token_hash=issued.digest,
        )
        self.stdout.write(issued.cleartext)
