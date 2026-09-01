from django.core.management.base import BaseCommand

from control.models import Server


class Command(BaseCommand):
    help = "Create or update the local VPS server record"

    def add_arguments(self, parser):
        parser.add_argument("--name", default="Personal VPS")
        parser.add_argument("--hostname", default="localhost")
        parser.add_argument("--agent-url", default="http://127.0.0.1:9743")

    def handle(self, *args, **options):
        server, created = Server.objects.update_or_create(
            name=options["name"],
            defaults={
                "hostname": options["hostname"],
                "agent_url": options["agent_url"],
                "is_active": True,
            },
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} server #{server.pk}: {server.name}"))
