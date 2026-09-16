from django.core.management.base import BaseCommand, CommandError

from control.models import ServiceCredential, ServicePrincipal
from control.security import issue_secret

READ_SCOPES = ["servers:read", "metrics:read", "services:read", "audit:read"]
OPERATOR_SCOPES = READ_SCOPES + ["operations:read", "operations:create", "logs:read"]
TELEGRAM_ADMIN_SCOPES = ["telegram:admin", "telegram:read", "telegram:publish"]
TELEGRAM_MCP_SCOPES = ["telegram:read", "telegram:publish"]

PROFILES = {
    "readonly": READ_SCOPES,
    "operator": OPERATOR_SCOPES,
    "telegram-admin": TELEGRAM_ADMIN_SCOPES,
    "telegram-mcp": TELEGRAM_MCP_SCOPES,
}


class Command(BaseCommand):
    help = "Create or reactivate a scoped service principal credential."

    def add_arguments(self, parser):
        parser.add_argument("name")
        parser.add_argument(
            "--profile",
            choices=sorted(PROFILES),
            default="readonly",
            help="Scope profile. Defaults to the existing read-only VPS profile.",
        )

    def handle(self, *args, **options):
        scopes = PROFILES[options["profile"]]
        principal, created = ServicePrincipal.objects.get_or_create(
            name=options["name"],
            defaults={"scopes": scopes},
        )
        if not created and principal.credentials.filter(revoked_at__isnull=True).exists():
            raise CommandError("principal already has an active credential")
        principal.scopes = scopes
        principal.is_active = True
        principal.save(update_fields=["scopes", "is_active"])
        issued = issue_secret("service")
        ServiceCredential.objects.create(
            principal=principal,
            token_prefix=issued.prefix,
            token_hash=issued.digest,
        )
        self.stdout.write(issued.cleartext)
