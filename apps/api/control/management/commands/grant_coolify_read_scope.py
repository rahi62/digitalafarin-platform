from django.core.management.base import BaseCommand

from control.models import ServicePrincipal


class Command(BaseCommand):
    help = "Grant coolify:read to existing active operator-like MCP principals without rotating credentials."

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            help="Upgrade only this principal. Without --name, upgrade active principals that already have operations:create.",
        )

    def handle(self, *args, **options):
        principals = ServicePrincipal.objects.filter(is_active=True)
        if options["name"]:
            principals = principals.filter(name=options["name"])

        updated = 0
        for principal in principals:
            scopes = list(principal.scopes or [])
            if not options["name"] and "operations:create" not in scopes:
                continue
            if "coolify:read" in scopes:
                continue
            scopes.append("coolify:read")
            principal.scopes = scopes
            principal.save(update_fields=["scopes"])
            updated += 1

        self.stdout.write(f"updated={updated}")
