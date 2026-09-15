import os

from cryptography.fernet import Fernet
from django.test import TestCase
from rest_framework.test import APIClient

from control.models import (
    EnvironmentVariable,
    Project,
    Server,
    Service,
    ServiceCredential,
    ServicePrincipal,
)
from control.security import issue_secret
from control.services.secrets import SecretConfigurationError, decrypt_secret, encrypt_secret
from control.services.variables import resolve_environment


class SecretServiceTests(TestCase):
    def setUp(self):
        self.key = Fernet.generate_key().decode()
        self.old = os.environ.get("PLATFORM_SECRET_KEYS")
        os.environ["PLATFORM_SECRET_KEYS"] = self.key

    def tearDown(self):
        if self.old is None:
            os.environ.pop("PLATFORM_SECRET_KEYS", None)
        else:
            os.environ["PLATFORM_SECRET_KEYS"] = self.old

    def test_secret_is_authenticated_and_versioned(self):
        ciphertext = encrypt_secret("sentinel-secret")

        self.assertTrue(ciphertext.startswith("v1:"))
        self.assertNotIn("sentinel-secret", ciphertext)
        self.assertEqual(decrypt_secret(ciphertext), "sentinel-secret")

    def test_wrong_key_cannot_decrypt(self):
        ciphertext = encrypt_secret("sentinel-secret")
        os.environ["PLATFORM_SECRET_KEYS"] = Fernet.generate_key().decode()

        with self.assertRaises(SecretConfigurationError):
            decrypt_secret(ciphertext)


class EnvironmentVariableAPITests(TestCase):
    def setUp(self):
        self.old = os.environ.get("PLATFORM_SECRET_KEYS")
        os.environ["PLATFORM_SECRET_KEYS"] = Fernet.generate_key().decode()
        self.project = Project.objects.create(name="Oily", slug="oily")
        server = Server.objects.create(name="Target")
        self.service = Service.objects.create(
            project=self.project,
            name="backend",
            repository="https://github.com/example/oily.git",
            branch="main",
            runtime="python-django",
            service_port=8000,
            target_server=server,
        )
        principal = ServicePrincipal.objects.create(
            name="platform-web",
            scopes=["operations:read", "operations:create"],
        )
        issued = issue_secret("service")
        ServiceCredential.objects.create(
            principal=principal,
            token_prefix=issued.prefix,
            token_hash=issued.digest,
        )
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")

    def tearDown(self):
        if self.old is None:
            os.environ.pop("PLATFORM_SECRET_KEYS", None)
        else:
            os.environ["PLATFORM_SECRET_KEYS"] = self.old

    def test_secret_create_and_list_never_return_plaintext_or_ciphertext(self):
        response = self.client.post(
            f"/api/control/v1/projects/{self.project.public_id}/variables/",
            {
                "key": "DATABASE_PASSWORD",
                "value": "sentinel-secret",
                "value_type": "secret",
                "scope": "service",
                "service_id": str(self.service.public_id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        serialized = str(response.json())
        self.assertNotIn("sentinel-secret", serialized)
        self.assertNotIn("ciphertext", serialized.lower())
        self.assertTrue(response.json()["has_value"])

        listed = self.client.get(
            f"/api/control/v1/projects/{self.project.public_id}/variables/"
        )
        self.assertNotIn("sentinel-secret", str(listed.json()))
        self.assertNotIn(
            EnvironmentVariable.objects.get().secret_ciphertext, str(listed.json())
        )

    def test_environment_scope_overrides_service_and_project(self):
        EnvironmentVariable.objects.create(
            project=self.project, key="MODE", value_type="plain", scope="project", plain_value="project"
        )
        EnvironmentVariable.objects.create(
            project=self.project, service=self.service, key="MODE", value_type="plain", scope="service", plain_value="service"
        )
        EnvironmentVariable.objects.create(
            project=self.project,
            service=self.service,
            key="MODE",
            value_type="plain",
            scope="environment",
            environment="production",
            plain_value="production",
        )

        values = resolve_environment(self.service, "production", include_secrets=False)

        self.assertEqual(values["MODE"], "production")
