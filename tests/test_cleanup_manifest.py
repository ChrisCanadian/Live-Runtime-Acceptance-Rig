from __future__ import annotations

import pytest

from live_runtime_rig.cleanup import CleanupManifest
from live_runtime_rig.contracts import CleanupEntry


def _entry(marker: str) -> CleanupEntry:
    return CleanupEntry(
        resource_type="work_order",
        identifier="example-id",
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
