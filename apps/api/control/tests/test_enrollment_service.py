from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from control.models import EnrollmentToken
from control.security import issue_secret
from control.services.enrollment import EnrollmentError, enroll_agent


class EnrollmentServiceTests(TestCase):
    def setUp(self):
        issued = issue_secret("enroll")
        self.secret = issued.cleartext
        self.row = EnrollmentToken.objects.create(
            token_prefix=issued.prefix,
            secret_hash=issued.digest,
            expires_at=timezone.now() + timedelta(minutes=10),
            created_by="test",
        )

    def test_enrollment_returns_server_specific_secret_once(self):
        result = enroll_agent(
            enrollment_secret=self.secret,
            name="VPS One",
            hostname="vps-one",
            agent_version="0.2.0",
            capabilities=["metrics", "systemd_inventory"],
        )

        self.assertIsNotNone(result.server.public_id)
        self.assertTrue(result.agent_token.startswith("da_agent_"))
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.used_at)

        with self.assertRaises(EnrollmentError):
            enroll_agent(
                enrollment_secret=self.secret,
                name="VPS Two",
                hostname="vps-two",
                agent_version="0.2.0",
                capabilities=[],
            )
