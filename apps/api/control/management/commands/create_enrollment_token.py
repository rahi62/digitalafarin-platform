from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from control.models import EnrollmentToken
from control.security import issue_secret


class Command(BaseCommand):
    help = "Create a one-time, expiring agent enrollment token."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=15)
        parser.add_argument("--created-by", default="operator")

    def handle(self, *args, **options):
        minutes = options["minutes"]
        if minutes < 1 or minutes > 1440:
            raise CommandError("--minutes must be between 1 and 1440")
        issued = issue_secret("enroll")
        EnrollmentToken.objects.create(
            token_prefix=issued.prefix,
            secret_hash=issued.digest,
            expires_at=timezone.now() + timedelta(minutes=minutes),
            created_by=options["created_by"],
        )
        self.stdout.write(issued.cleartext)
