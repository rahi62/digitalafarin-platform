from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from control.models import Server
from control.services.deployments import DeploymentAdmissionError, deployment_admission


class DeploymentAdmissionTests(TestCase):
    def test_disk_below_warning_is_allowed(self):
        server = Server.objects.create(name="Target", last_seen_at=timezone.now(), disk_percent=79.9)
        self.assertEqual(deployment_admission(server), {"allowed": True, "warning": False})

    def test_disk_at_eighty_warns_and_ninety_blocks(self):
        server = Server.objects.create(name="Target", last_seen_at=timezone.now(), disk_percent=80)
        self.assertEqual(deployment_admission(server), {"allowed": True, "warning": True})
        server.disk_percent = 90
        server.save(update_fields=["disk_percent"])
        with self.assertRaises(DeploymentAdmissionError):
            deployment_admission(server)

    def test_stale_disk_snapshot_blocks(self):
        server = Server.objects.create(
            name="Target",
            last_seen_at=timezone.now() - timedelta(seconds=121),
            disk_percent=10,
        )
        with self.assertRaises(DeploymentAdmissionError):
            deployment_admission(server)
