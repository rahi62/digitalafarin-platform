from digitalafarin_agent.redaction import redact


def test_redaction_removes_credentials_and_known_secret_values():
    text = "Authorization: Bearer abc123 DATABASE_URL=postgres://user:pass@db/app known-value"

    output = redact(text, known_secrets=("known-value",))

    assert "abc123" not in output
    assert "user:pass" not in output
    assert "known-value" not in output
    assert output.count("[REDACTED]") >= 3


def test_redaction_removes_private_key_block():
    text = "before\n-----BEGIN PRIVATE KEY-----\nprivate-material\n-----END PRIVATE KEY-----\nafter"

    output = redact(text)

    assert "private-material" not in output
    assert "before" in output and "after" in output
