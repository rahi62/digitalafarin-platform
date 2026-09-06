import os
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from control.models import (
    ServiceCredential,
    ServicePrincipal,
    TelegramBotCredential,
    TelegramChannel,
    TelegramPublishAudit,
)
from control.security import issue_secret
from control.telegram_crypto import decrypt_bot_token


TEST_FERNET_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


class FakeTelegramClient:
    sent = []

    def __init__(self, token):
        self.token = token

    def validate_bot(self):
        return {"id": 42, "username": "digitalafarin_test_bot"}

    def send_message(self, chat_id, text, disable_web_page_preview=False):
        self.__class__.sent.append(
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": disable_web_page_preview,
            }
        )
        return [{"message_id": 101}, {"message_id": 102}] if len(text) > 4096 else [{"message_id": 101}]


class TelegramAPITests(TestCase):
    def setUp(self):
        FakeTelegramClient.sent = []
        self.env_patch = patch.dict(
            os.environ,
            {"TELEGRAM_CREDENTIAL_ENCRYPTION_KEY": TEST_FERNET_KEY},
            clear=False,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def _client_for(self, name, scopes):
        principal = ServicePrincipal.objects.create(name=name, scopes=scopes)
        issued = issue_secret("service")
        ServiceCredential.objects.create(
            principal=principal,
            token_prefix=issued.prefix,
            token_hash=issued.digest,
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {issued.cleartext}")
        return client

    @patch("control.telegram_views.TelegramClient", FakeTelegramClient)
    def test_admin_can_replace_bot_credential_without_reading_plaintext_back(self):
        client = self._client_for(
            "telegram-web",
            ["telegram:admin", "telegram:read", "telegram:publish"],
        )

        response = client.put(
            "/api/control/v1/telegram/bot-credential/",
            {"token": "123456:SECRET_TEST_TOKEN", "name": "primary"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["configured"], True)
        self.assertNotIn("token", response.json())
        credential = TelegramBotCredential.objects.get(name="primary")
        self.assertEqual(decrypt_bot_token(credential.token_ciphertext), "123456:SECRET_TEST_TOKEN")

        status_response = client.get("/api/control/v1/telegram/status/")
        self.assertEqual(status_response.status_code, 200)
        self.assertTrue(status_response.json()["bot_configured"])
        self.assertNotIn("token", status_response.json())

    def test_admin_can_create_channel_and_read_client_can_list_active_aliases(self):
        admin = self._client_for(
            "telegram-admin",
            ["telegram:admin", "telegram:read", "telegram:publish"],
        )
        reader = self._client_for("telegram-reader", ["telegram:read"])

        created = admin.post(
            "/api/control/v1/telegram/channels/",
            {
                "alias": "SEO",
                "name": "SEO Channel",
                "chat_id": "@digitalafarin_seo",
                "description": "Search content",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["alias"], "seo")

        listed = reader.get("/api/control/v1/telegram/channels/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["items"][0]["alias"], "seo")

    def test_invalid_channel_alias_returns_validation_error(self):
        admin = self._client_for(
            "telegram-admin-invalid-alias",
            ["telegram:admin", "telegram:read", "telegram:publish"],
        )

        response = admin.post(
            "/api/control/v1/telegram/channels/",
            {
                "alias": "SEO channel!",
                "name": "Bad Channel",
                "chat_id": "@bad_channel",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("alias", response.json())

    @patch("control.telegram_views.TelegramClient", FakeTelegramClient)
    def test_publish_scope_can_publish_and_creates_audit(self):
        TelegramBotCredential.objects.create(
            name="primary",
            token_ciphertext="gAAAAABplaceholder",
            is_active=True,
        )
        # Patch decrypt separately so this test focuses on publish authorization/data flow.
        TelegramChannel.objects.create(
            alias="seo",
            name="SEO",
            chat_id="@digitalafarin_seo",
            is_active=True,
        )
        publisher = self._client_for("telegram-mcp", ["telegram:read", "telegram:publish"])

        with patch("control.telegram_views.decrypt_bot_token", return_value="123456:TEST"):
            response = publisher.post(
                "/api/control/v1/telegram/publish/",
                {
                    "channel": "seo",
                    "text": "Hello from ChatGPT",
                    "disable_web_page_preview": True,
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["channel"], "seo")
        self.assertEqual(response.json()["message_ids"], [101])
        self.assertEqual(FakeTelegramClient.sent[0]["chat_id"], "@digitalafarin_seo")
        audit = TelegramPublishAudit.objects.get(action="publish")
        self.assertEqual(audit.status, "success")
        self.assertEqual(audit.actor_principal, "telegram-mcp")
        self.assertEqual(audit.message_ids, [101])

    def test_read_only_scope_cannot_publish(self):
        reader = self._client_for("telegram-reader-only", ["telegram:read"])

        response = reader.post(
            "/api/control/v1/telegram/publish/",
            {"channel": "seo", "text": "should not send"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    @patch("control.telegram_views.TelegramClient", FakeTelegramClient)
    def test_admin_can_test_channel_and_result_is_audited(self):
        TelegramBotCredential.objects.create(
            name="primary",
            token_ciphertext="gAAAAABplaceholder",
            is_active=True,
        )
        channel = TelegramChannel.objects.create(
            alias="seo",
            name="SEO",
            chat_id="@digitalafarin_seo",
            is_active=True,
        )
        admin = self._client_for(
            "telegram-admin-test",
            ["telegram:admin", "telegram:read", "telegram:publish"],
        )

        with patch("control.telegram_views.decrypt_bot_token", return_value="123456:TEST"):
            response = admin.post(
                f"/api/control/v1/telegram/channels/{channel.public_id}/test/",
                {},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(TelegramPublishAudit.objects.filter(action="test", status="success").exists())
