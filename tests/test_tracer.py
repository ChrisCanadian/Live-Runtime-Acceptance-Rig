from __future__ import annotations

import json
from datetime import datetime

import pytest

from live_runtime_rig.redaction import Redactor
from live_runtime_rig.tracer import Tracer


def test_tracer_writes_timestamp_sequence_and_span_elapsed_time(tmp_path) -> None:
    path = tmp_path / "nested" / "trace.ndjson"
    tracer = Tracer(path, "ACCEPTANCE_TEST")
    tracer.emit("campaign.execution", phase="started")
    with tracer.span("case.execution", suite="example", case="create"):
        pass

    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["sequence"] for record in records] == [1, 2, 3]
    assert all(record["run_id"] == "ACCEPTANCE_TEST" for record in records)
    assert all(datetime.fromisoformat(record["timestamp"]).tzinfo for record in records)
    assert records[-1]["success"] is True
    assert records[-1]["elapsed_ms"] >= 0


def test_tracer_records_safe_exception_type(tmp_path) -> None:
    path = tmp_path / "trace.ndjson"
    tracer = Tracer(path, "ACCEPTANCE_TEST")
    with pytest.raises(ValueError):
        with tracer.span("case.execution"):
            raise ValueError("protected message")
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["exception_type"] == "ValueError"
    assert "protected message" not in json.dumps(record)


def test_protected_text_helper_hashes_without_returning_text() -> None:
    protected = "private sample"
    metadata = Tracer.protected_text_metadata(protected)
    assert metadata["length"] == len(protected)
    assert len(metadata["sha256"]) == 64
    assert protected not in str(metadata)


def test_tracer_applies_redaction(tmp_path) -> None:
    path = tmp_path / "trace.ndjson"
    tracer = Tracer(
        path,
        "ACCEPTANCE_TEST",
        redactor=Redactor(secrets=["sample-secret"], environment_values=[]),
    )
    header = "Authorization" + ": " + "Bearer " + "sample-secret"
    tracer.emit("example", value=header)
    text = path.read_text(encoding="utf-8")
    assert "sample-secret" not in text
    assert "REDACTED" in text
