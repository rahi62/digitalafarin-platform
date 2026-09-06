import os
from unittest.mock import patch

from django.test import TestCase

from control.models import TelegramBotCredential, TelegramChannel
from control.telegram_crypto import decrypt_bot_token, encrypt_bot_token


TEST_FERNET_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


class TelegramModelTests(TestCase):
    def test_channel_alias_is_normalized_before_save(self):
        channel = TelegramChannel.objects.create(
            alias="  SEO  ",
            name="SEO",
            chat_id="@digitalafarin_seo",
        )

        self.assertEqual(channel.alias, "seo")

    def test_bot_token_is_encrypted_and_round_trips(self):
        with patch.dict(
            os.environ,
            {"TELEGRAM_CREDENTIAL_ENCRYPTION_KEY": TEST_FERNET_KEY},
            clear=False,
        ):
            plaintext = "123456:TEST_TOKEN"
            ciphertext = encrypt_bot_token(plaintext)
            TelegramBotCredential.objects.create(
                name="primary",
                token_ciphertext=ciphertext,
            )

            stored = TelegramBotCredential.objects.get(name="primary")
            self.assertNotIn(plaintext, stored.token_ciphertext)
            self.assertEqual(decrypt_bot_token(stored.token_ciphertext), plaintext)

    def test_channel_alias_rejects_invalid_characters(self):
        channel = TelegramChannel(
            alias="seo channel!",
            name="SEO",
            chat_id="@digitalafarin_seo",
        )

        with self.assertRaisesMessage(ValueError, "invalid channel alias"):
            channel.save()
