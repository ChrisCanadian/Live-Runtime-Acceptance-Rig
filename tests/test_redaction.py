from __future__ import annotations

from live_runtime_rig.redaction import Redactor


def test_public_safe_redaction_removes_sensitive_values_and_paths() -> None:
    redactor = Redactor(
        secrets=["top-secret-value"],
        environment_values=["example-machine"],
    )
    sample_value = "top-secret-value"
    authorization = "Authorization" + ": " + "Bearer " + sample_value
    password_assignment = "password" + "=" + sample_value
    windows_path = "C:" + "\\" + "Users\\sample\\work\\database.sqlite"
    source = " ".join(
        (authorization, password_assignment, windows_path, "host=example-machine")
    )
    redacted = redactor.redact_text(source)
    assert sample_value not in redacted
    assert "example-machine" not in redacted
    assert windows_path not in redacted
    assert "REDACTED" in redacted


def test_redaction_recurses_through_structured_values() -> None:
    redactor = Redactor(secrets=["secret-value"], environment_values=[])
    payload = {"nested": ["secret-value", {"token": "Bearer abc123"}]}
    redacted = redactor.redact_value(payload)
    assert "secret-value" not in str(redacted)
    assert "abc123" not in str(redacted)
