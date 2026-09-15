import re
from collections.abc import Iterable


_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)(\b(?:password|passwd|secret|token|api_key)\s*[=:]\s*)[^\s]+"),
    re.compile(r"(?i)(postgres(?:ql)?://[^:/\s]+:)[^@\s]+(@[^\s]+)"),
    re.compile(r"da_(?:agent|service|enroll)_[A-Za-z0-9]+\.[A-Za-z0-9_-]+"),
    re.compile(
        r"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----.*?-----END (?:[A-Z ]+)?PRIVATE KEY-----",
        re.DOTALL,
    ),
)


def redact(text: str, known_secrets: Iterable[str] = ()) -> str:
    output = str(text)
    for secret in known_secrets:
        if secret:
            output = output.replace(secret, "[REDACTED]")
    output = _PATTERNS[0].sub(r"\1[REDACTED]", output)
    output = _PATTERNS[1].sub(r"\1[REDACTED]", output)
    output = _PATTERNS[2].sub(r"\1[REDACTED]\2", output)
    output = _PATTERNS[3].sub("[REDACTED]", output)
    output = _PATTERNS[4].sub("[REDACTED PRIVATE KEY]", output)
    return output
