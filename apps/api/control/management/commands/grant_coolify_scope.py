from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from control.models import AuditEvent, ServicePrincipal


class Command(BaseCommand):
    help = "Explicitly grant one Coolify scope to an active service principal; never rotate or print credentials."

    def add_arguments(self, parser):
        parser.add_argument("name")
        parser.add_argument("--scope", required=True, choices=["coolify:read", "coolify:deploy", "coolify:manage", "coolify:delete"])

    @transaction.atomic
    def handle(self, *args, **options):
        principal = ServicePrincipal.objects.select_for_update().filter(name=options["name"], is_active=True).first()
        if principal is None:
            raise CommandError("Active principal not found.")
        scope = options["scope"]
        if scope not in principal.scopes:
            principal.scopes = [*principal.scopes, scope]
            principal.save(update_fields=["scopes"])
            AuditEvent.objects.create(event_type="coolify.scope.granted", actor="management-command", target_type="service_principal", target_id=str(principal.pk), metadata={"scope": scope})
        self.stdout.write("Coolify scope granted; credentials unchanged.")
