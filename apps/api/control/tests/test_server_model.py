from datetime import timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from control.models import Server


class ServerModelTests(TestCase):
    def test_public_id_is_uuid_and_unique(self):
        first = Server.objects.create(name="primary")
        second = Server.objects.create(name="secondary")

        self.assertIsInstance(first.public_id, UUID)
        self.assertNotEqual(first.public_id, second.public_id)

    def test_status_is_derived_from_last_seen(self):
        now = timezone.now()
        server = Server.objects.create(
            name="primary",
            last_seen_at=now - timedelta(seconds=10),
        )

        self.assertEqual(server.status_at(now), "online")
        server.last_seen_at = now - timedelta(seconds=60)
        self.assertEqual(server.status_at(now), "stale")
        server.last_seen_at = now - timedelta(seconds=121)
        self.assertEqual(server.status_at(now), "offline")

    def test_never_seen_server_is_offline(self):
        server = Server.objects.create(name="primary")

        self.assertIsNone(server.age_seconds)
        self.assertEqual(server.status, "offline")
        self.assertTrue(server.is_stale)

    def test_only_one_active_default_is_allowed(self):
        Server.objects.create(name="primary", is_active=True, is_default=True)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Server.objects.create(
                    name="secondary",
                    is_active=True,
                    is_default=True,
                )
