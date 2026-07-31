from __future__ import annotations

import pytest

from live_runtime_rig.cleanup import CleanupManifest
from live_runtime_rig.contracts import CleanupEntry


def _entry(
    marker: str,
    *,
    identifier: str = "example-id",
    resource_type: str = "work_order",
) -> CleanupEntry:
    return CleanupEntry(
        resource_type=resource_type,
        identifier=identifier,
        table_or_path="work_orders",
        run_marker=marker,
        notes="Created by the current run.",
        cleanup_key="example.remove_exact_work_order",
        cleanup_instruction="Require both identifier and marker.",
    )


def test_cleanup_manifest_contains_only_current_run_entries() -> None:
    manifest = CleanupManifest("ACCEPTANCE_TEST", "ACCEPTANCE_TEST")
    manifest.add(_entry("ACCEPTANCE_TEST"))
    payload = manifest.as_dict()
    assert payload["automatic_cleanup_performed"] is False
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["run_marker"] == "ACCEPTANCE_TEST"


def test_cleanup_manifest_rejects_foreign_marker() -> None:
    manifest = CleanupManifest("ACCEPTANCE_TEST", "ACCEPTANCE_TEST")
    with pytest.raises(ValueError, match="does not match"):
        manifest.add(_entry("ANOTHER_RUN"))


@pytest.mark.parametrize("identifier", ["", "   "])
def test_cleanup_manifest_rejects_empty_identifier(identifier: str) -> None:
    manifest = CleanupManifest("ACCEPTANCE_TEST", "ACCEPTANCE_TEST")
    with pytest.raises(ValueError, match="identifier"):
        manifest.add(_entry("ACCEPTANCE_TEST", identifier=identifier))


def test_duplicate_cleanup_registration_is_idempotent() -> None:
    manifest = CleanupManifest("ACCEPTANCE_TEST", "ACCEPTANCE_TEST")
    entry = _entry("ACCEPTANCE_TEST")
    manifest.add(entry)
    manifest.add(entry)
    assert manifest.entries == (entry,)


def test_cleanup_batch_validation_is_atomic() -> None:
    manifest = CleanupManifest("ACCEPTANCE_TEST", "ACCEPTANCE_TEST")
    valid = _entry("ACCEPTANCE_TEST", identifier="valid")
    invalid = _entry("ANOTHER_RUN", identifier="invalid")

    with pytest.raises(ValueError, match="does not match"):
        manifest.add_many((valid, invalid))

    assert manifest.entries == ()


def test_cleanup_batch_adds_multiple_unique_entries() -> None:
    manifest = CleanupManifest("ACCEPTANCE_TEST", "ACCEPTANCE_TEST")
    first = _entry("ACCEPTANCE_TEST", identifier="first")
    second = _entry(
        "ACCEPTANCE_TEST",
        identifier="second",
        resource_type="event",
    )
    manifest.add_many((first, second, first))
    assert manifest.entries == (first, second)