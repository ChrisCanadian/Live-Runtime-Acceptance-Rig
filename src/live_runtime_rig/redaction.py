"""Conservative public-safe redaction helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable


_AUTHORIZATION = re.compile(
    r"(?i)\b(authorization)\s*[:=]\s*([^\s,;]+(?:\s+[^\s,;]+)?)"
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)"
    r"\s*[:=]\s*([^\s,;]+)"
)
_WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:\\(?:[^<>:\"|?*\r\n]+\\)*[^<>:\"|?*\r\n]*")
_POSIX_PRIVATE_PATH = re.compile(
    r"(?<![\w:])/(?:home|Users|private|var|tmp|opt)/[^\s\"'<>]+"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_DATABASE_FILE = re.compile(r"(?i)\b[^\s\"'<>]+\.(?:db|sqlite|sqlite3)\b")


def _default_environment_values() -> list[str]:
    sensitive_keys = (
        "TOKEN",
        "SECRET",
        "PASSWORD",
        "API_KEY",
        "AUTH",
        "USERPROFILE",
        "HOME",
        "USERNAME",
        "HOSTNAME",
        "COMPUTERNAME",
    )
    values: list[str] = []
    for key, value in os.environ.items():
        upper = key.upper()
        if value and len(value) >= 4 and any(part in upper for part in sensitive_keys):
            values.append(value)
    return values


class Redactor:
    """Redacts structured values before they enter public-safe evidence."""

    def __init__(
        self,
        *,
        secrets: Iterable[str] = (),
        environment_values: Iterable[str] | None = None,
    ) -> None:
        combined = list(secrets)
        combined.extend(
            _default_environment_values()
            if environment_values is None
            else environment_values
        )
        self._literal_values = sorted(
            {str(value) for value in combined if value and len(str(value)) >= 4},
            key=len,
            reverse=True,
        )

    def redact_text(self, value: str) -> str:
        result = value
        for secret in self._literal_values:
            result = result.replace(secret, "[REDACTED_VALUE]")
        result = _AUTHORIZATION.sub(r"\1: [REDACTED_AUTHORIZATION]", result)
        result = _SENSITIVE_ASSIGNMENT.sub(r"\1=[REDACTED_SECRET]", result)
        result = _BEARER.sub("Bearer [REDACTED_TOKEN]", result)
        result = _WINDOWS_PATH.sub("[REDACTED_PATH]", result)
        result = _POSIX_PRIVATE_PATH.sub("[REDACTED_PATH]", result)
        result = _DATABASE_FILE.sub("[REDACTED_DATABASE_PATH]", result)
        return result

    def redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Path):
            return self.redact_text(str(value))
        if isinstance(value, dict):
            return {
                self.redact_text(str(key)): self.redact_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [self.redact_value(item) for item in value]
        return value
