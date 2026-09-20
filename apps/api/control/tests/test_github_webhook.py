import hashlib
import hmac
import json
import os

from cryptography.fernet import Fernet
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from control.models import (
    Deployment,
    EnvironmentVariable,
    GitHubDelivery,
    Operation,
    Project,
    Server,
    Service,
)
from control.services.secrets import encrypt_secret


class GitHubWebhookTests(TestCase):
    def setUp(self):
        self.old = os.environ.get("PLATFORM_SECRET_KEYS")
        os.environ["PLATFORM_SECRET_KEYS"] = Fernet.generate_key().decode()
        server = Server.objects.create(name="Target", last_seen_at=timezone.now(), disk_percent=20)
        project = Project.objects.create(name="Oily", slug="oily")
        self.service = Service.objects.create(
            project=project, name="web", unit_name="oily-web.service", repository="https://github.com/example/oily.git",
            lifecycle_state=Service.LIFECYCLE_MANAGED,
            branch="main", runtime="node-nextjs", service_port=3000, target_server=server,
        )
        EnvironmentVariable.objects.create(
            project=project, service=self.service, key="GITHUB_WEBHOOK_SECRET", value_type="secret",
            scope="service", secret_ciphertext=encrypt_secret("webhook-sentinel"),
        )
        self.client = APIClient()

    def tearDown(self):
        if self.old is None:
            os.environ.pop("PLATFORM_SECRET_KEYS", None)
        else:
            os.environ["PLATFORM_SECRET_KEYS"] = self.old

    def send(self, delivery="delivery-1", valid=True):
        payload = json.dumps({
            "ref": "refs/heads/main", "after": "c" * 40,
            "repository": {"html_url": "https://github.com/example/oily"},
        }).encode()
        signature = hmac.new(b"webhook-sentinel" if valid else b"wrong", payload, hashlib.sha256).hexdigest()
        return self.client.post(
            "/api/control/v1/github/webhook/", payload, content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=f"sha256={signature}", HTTP_X_GITHUB_DELIVERY=delivery,
            HTTP_X_GITHUB_EVENT="push",
        )

    def test_signature_is_verified_and_delivery_is_deduplicated(self):
        first = self.send()
        duplicate = self.send()

        self.assertEqual(first.status_code, 202)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(GitHubDelivery.objects.count(), 1)

    def test_configured_service_cannot_deploy_from_github_webhook(self):
        self.service.lifecycle_state = Service.LIFECYCLE_CONFIGURED
        self.service.save(update_fields=["lifecycle_state"])

        response = self.send(delivery="configured-service")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Deployment.objects.count(), 0)
        self.assertEqual(Operation.objects.count(), 0)

    def test_invalid_signature_creates_nothing(self):
        response = self.send(valid=False)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(GitHubDelivery.objects.count(), 0)
