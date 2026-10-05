from unittest.mock import patch

from django.core import signing
from django.test import TestCase
from rest_framework.test import APIClient

from control.models import GitHubInstallation, ServiceCredential, ServicePrincipal
from control.security import issue_secret


class GitHubIntegrationTests(TestCase):
    def setUp(self):
        principal = ServicePrincipal.objects.create(
            name="platform-web-github",
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

    @patch.dict("os.environ", {
        "GITHUB_APP_ID": "123",
        "GITHUB_APP_PRIVATE_KEY": "key",
        "GITHUB_APP_WEBHOOK_SECRET": "secret",
        "GITHUB_APP_SLUG": "digitalafarin",
    })
    def test_integration_status_exposes_install_url_without_credentials(self):
        response = self.client.get("/api/control/v1/github/integration/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["configured"])
        self.assertIn("github.com/apps/digitalafarin/installations/new?state=", body["install_url"])
        self.assertNotIn("secret", str(body).lower())
        self.assertNotIn("private_key", str(body).lower())

    @patch("control.github_views.installation_details")
    def test_installation_callback_requires_signed_short_lived_state(self, details):
        details.return_value = {
            "installation_id": 42,
            "account_login": "rahi62",
            "account_type": "User",
            "repository_selection": "selected",
            "suspended": False,
        }
        invalid = self.client.post(
            "/api/control/v1/github/installations/",
            {"installation_id": 42, "state": "invalid"},
            format="json",
        )
        self.assertEqual(invalid.status_code, 409)
        state = signing.dumps({"purpose": "github-install"}, salt="github-install")
        valid = self.client.post(
            "/api/control/v1/github/installations/",
            {"installation_id": 42, "state": state},
            format="json",
        )
        self.assertEqual(valid.status_code, 200)
        self.assertTrue(GitHubInstallation.objects.filter(installation_id=42).exists())

    @patch("control.github_views.installation_repositories")
    def test_repository_list_uses_registered_non_suspended_installation(self, repositories):
        GitHubInstallation.objects.create(
            installation_id=42,
            account_login="rahi62",
            repository_selection="selected",
        )
        repositories.return_value = [{
            "id": 1,
            "full_name": "rahi62/app",
            "html_url": "https://github.com/rahi62/app",
            "default_branch": "main",
            "private": True,
        }]
        response = self.client.get("/api/control/v1/github/installations/42/repositories/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["full_name"], "rahi62/app")


    @patch.dict("os.environ", {
        "GITHUB_APP_ID": "123",
        "GITHUB_APP_PRIVATE_KEY": "",
        "GITHUB_APP_PRIVATE_KEY_FILE": "/etc/digitalafarin-platform/github-app-private-key.pem",
        "GITHUB_APP_WEBHOOK_SECRET": "secret",
        "GITHUB_APP_SLUG": "digitalafarin",
    }, clear=False)
    def test_integration_accepts_private_key_file_configuration(self):
        response = self.client.get("/api/control/v1/github/integration/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["configured"])
