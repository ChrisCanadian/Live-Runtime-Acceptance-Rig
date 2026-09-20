from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from live_runtime_rig.assertions import CheckStatus
from live_runtime_rig.config import RigConfig
from live_runtime_rig.console import Console
from live_runtime_rig.contracts import BackupProof, CaseResult, CheckSpec, CleanupEntry
from live_runtime_rig.evidence import EvidenceBundle
from live_runtime_rig.redaction import Redactor
from live_runtime_rig.runner import RigRunner
from live_runtime_rig.tracer import Tracer
from live_runtime_rig_examples.fastapi_sqlite.database_adapter import (
    WorkOrderDatabaseAdapter,
)


class FakeRuntime:
    def __init__(self, *, fail_close: bool = False) -> None:
        self.fail_close = fail_close

    def start(self) -> None:
        pass

    def close(self) -> None:
        if self.fail_close:
            raise RuntimeError("close failed")

    def health(self):
        return {"ready": True}

    def direct_readiness_probe(self):
        return {"ready": True}

    def list_capabilities(self):
        return ()


class FakeDatabase:
    def __init__(self) -> None:
        self.resources: list[str] = []
        self.closed = False

    def verify_connection(self):
        return {"connected": True}

    def backup(self, destination: Path):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"valid backup")
        return BackupProof(
            evidence_type="file",
            target=str(destination.resolve()),
            verified=True,
            integrity="ok",
            size_bytes=destination.stat().st_size,
            sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
            method="fake-copy",
        )

    def integrity_check(self, path: Path | None = None):
        return {"result": "ok"}

    def snapshot_state(self):
        return {"resources": list(self.resources)}

    def protected_state_snapshot(self):
        return {"protected": "unchanged"}

    def cleanup_manifest_entry(
        self,
        resource_type: str,
        identifier: str,
        marker: str,
        *,
        notes: str = "",
    ) -> CleanupEntry:
        return CleanupEntry(resource_type, identifier, "resources", marker, notes)

    def close(self) -> None:
        self.closed = True


class PassingCase:
    name = "passing"
    suite = "acceptance"

    def run(self, runtime, database, context):
        return CaseResult([CheckSpec("executed", CheckStatus.PASS, True, True)])


class SkippedCase:
    name = "skipped"
    suite = "acceptance"

    def run(self, runtime, database, context):
        return CaseResult([CheckSpec("not executed", CheckStatus.SKIP, True, False)])


class ProbeFailure(RuntimeError):
    pass


class ExplodingCase:
    name = "exploding"
    suite = "acceptance"

    def run(self, runtime, database, context):
        raise ProbeFailure("boom")


class MutateThenFailCase:
    name = "partial_write"
    suite = "acceptance"

    def run(self, runtime, database, context):
        database.resources.append("resource-1")
        context.register_cleanup(
            database.cleanup_manifest_entry(
                "record", "resource-1", context.marker
            )
        )
        raise ProbeFailure("after durable write")


class MultipleMutationsThenFailCase:
    name = "multiple_partial_writes"
    suite = "acceptance"

    def run(self, runtime, database, context):
        for identifier in ("resource-1", "resource-2"):
            database.resources.append(identifier)
            context.register_cleanup(
                database.cleanup_manifest_entry(
                    "record", identifier, context.marker
                )
            )
        raise ProbeFailure("after multiple durable writes")


def _config(tmp_path: Path) -> RigConfig:
    config_file = tmp_path / ".env"
    config_file.write_text("# probe config\n", encoding="utf-8")
    return RigConfig(
        config_file=config_file,
        runtime_adapter="unused:runtime",
        database_adapter="unused:database",
        cases="unused:cases",
        database_path=tmp_path / "database.sqlite",
        evidence_dir=tmp_path / "evidence",
        application_label="failure-mode-probe",
    )


def _runner(tmp_path: Path, cases, *, runtime=None, database=None, run_id="PROBE"):
    database = database or FakeDatabase()
    runtime = runtime or FakeRuntime()
    return RigRunner(
        _config(tmp_path),
        run_id=run_id,
        runtime_factory=lambda _: runtime,
        database_factory=lambda _: database,
        case_loader=lambda _: cases,
        console=Console(quiet=True, stream=io.StringIO()),
    ), database


def _run_payload(runner: RigRunner) -> dict:
    return json.loads((runner.evidence.root / "run.json").read_text(encoding="utf-8"))


def test_partial_write_is_registered_before_case_exception(tmp_path) -> None:
    runner, database = _runner(tmp_path, [MutateThenFailCase()])

    assert runner.run() == 1
    cleanup = json.loads(
        (runner.evidence.root / "cleanup_manifest.json").read_text(encoding="utf-8")
    )

    assert database.resources == ["resource-1"]
    assert [entry["identifier"] for entry in cleanup["entries"]] == ["resource-1"]


def test_multiple_partial_writes_have_complete_manifest_after_exception(
    tmp_path,
) -> None:
    runner, database = _runner(tmp_path, [MultipleMutationsThenFailCase()])
    assert runner.run() == 1
    cleanup = json.loads(
        (runner.evidence.root / "cleanup_manifest.json").read_text(encoding="utf-8")
    )
    assert database.resources == ["resource-1", "resource-2"]
    assert [entry["identifier"] for entry in cleanup["entries"]] == [
        "resource-1",
        "resource-2",
    ]


def test_false_backup_metadata_without_file_blocks_campaign(tmp_path) -> None:
    class LyingDatabase(FakeDatabase):
        def backup(self, destination: Path):
            return {
                "verified": True,
                "integrity": "ok",
                "size_bytes": 1,
                "sha256": "a" * 64,
                "path": str(destination),
            }

    runner, _ = _runner(tmp_path, [PassingCase()], database=LyingDatabase())
    assert runner.run() == 1


def test_case_exception_trace_matches_failed_ledger(tmp_path) -> None:
    runner, _ = _runner(tmp_path, [ExplodingCase()])
    assert runner.run() == 1
    records = [
        json.loads(line)
        for line in (runner.evidence.root / "trace.ndjson")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    completed = [
        item
        for item in records
        if item["event"] == "case.execution" and item["phase"] == "completed"
    ][0]
    assert completed["success"] is False
    assert completed["exception_type"] == "ProbeFailure"


@pytest.mark.parametrize("cases", [[], [SkippedCase()]])
def test_campaign_without_executed_acceptance_check_is_inconclusive(
    tmp_path, cases
) -> None:
    runner, _ = _runner(tmp_path, cases)
    assert runner.run() == 1
    result = _run_payload(runner)
    assert result["acceptance_status"] == "INCONCLUSIVE"
    assert result["result_code"] == "NO_EXECUTED_ACCEPTANCE_CHECKS"


def test_trace_runtime_metadata_cannot_be_overridden(tmp_path) -> None:
    tracer = Tracer(tmp_path / "trace.ndjson", "REAL_RUN")
    with pytest.raises(ValueError, match="reserved"):
        tracer.emit(
            "event",
            run_id="forged",
            sequence=999,
            timestamp="forged",
        )


@pytest.mark.parametrize(
    "relative_path",
    ["../escaped.txt", "nested/../../escaped.txt"],
)
def test_evidence_writes_cannot_escape_run_root(tmp_path, relative_path) -> None:
    bundle = EvidenceBundle(
        tmp_path / "evidence",
        "SAFE_RUN",
        public_safe=False,
        redactor=Redactor(environment_values=[]),
    )
    with pytest.raises(ValueError, match="evidence root"):
        bundle.write_text(relative_path, "escaped")


def test_absolute_evidence_path_is_rejected(tmp_path) -> None:
    bundle = EvidenceBundle(
        tmp_path / "evidence",
        "SAFE_RUN",
        public_safe=False,
        redactor=Redactor(environment_values=[]),
    )
    with pytest.raises(ValueError, match="evidence root"):
        bundle.write_text(str(tmp_path / "absolute.txt"), "escaped")


def test_programmatic_run_id_cannot_escape_evidence_root(tmp_path) -> None:
    with pytest.raises(ValueError, match="run_id"):
        EvidenceBundle(
            tmp_path / "evidence",
            "../escaped-run",
            public_safe=False,
            redactor=Redactor(environment_values=[]),
        )


def test_ambient_configuration_override_requires_opt_in_and_records_provenance(
    tmp_path,
) -> None:
    config_file = tmp_path / ".env"
    config_file.write_text(
        "\n".join(
            (
                "RIG_RUNTIME_ADAPTER=file:runtime",
                "RIG_DATABASE_ADAPTER=file:database",
                "RIG_CASES=file:cases",
                "RIG_DATABASE_PATH=file.sqlite",
                "RIG_EVIDENCE_DIR=evidence",
                "RIG_APPLICATION_LABEL=file-label",
            )
        ),
        encoding="utf-8",
    )
    config = RigConfig.load(
        config_file,
        environment={"RIG_APPLICATION_LABEL": "ambient-label"},
    )
    assert config.application_label == "file-label"
    assert config.provenance["RIG_APPLICATION_LABEL"] == "config file"


def test_duplicate_case_evidence_names_are_rejected_before_execution(tmp_path) -> None:
    first = PassingCase()
    first.name = "duplicate/name"
    second = PassingCase()
    second.name = "duplicate_name"
    runner, _ = _runner(tmp_path, [first, second])
    assert runner.run() == 1
    assert _run_payload(runner)["result_code"] == "DUPLICATE_CASE_EVIDENCE_NAME"


def test_non_json_object_cannot_bypass_public_safe_redaction(tmp_path) -> None:
    class SecretObject:
        def __str__(self) -> str:
            return "top-secret-object-value"

    bundle = EvidenceBundle(
        tmp_path / "evidence",
        "SAFE_RUN",
        public_safe=True,
        redactor=Redactor(environment_values=[]),
    )
    with pytest.raises(TypeError, match="JSON-compatible"):
        bundle.write_json("artifact.json", {"value": SecretObject()})


def test_protected_text_hashes_are_not_stable_across_runs(tmp_path) -> None:
    first = Tracer(tmp_path / "first.ndjson", "FIRST")
    second = Tracer(tmp_path / "second.ndjson", "SECOND")
    assert first.protected_text_metadata("yes") != second.protected_text_metadata("yes")


def test_adapter_close_failures_mark_framework_error(tmp_path) -> None:
    runner, _ = _runner(
        tmp_path,
        [PassingCase()],
        runtime=FakeRuntime(fail_close=True),
    )
    assert runner.run() == 1
    assert _run_payload(runner)["framework_status"] == "ERROR"


def test_database_adapter_is_closed(tmp_path) -> None:
    runner, database = _runner(tmp_path, [PassingCase()])
    runner.run()
    assert database.closed is True


def test_example_database_adapter_does_not_mutate_during_initialization(tmp_path) -> None:
    database_path = tmp_path / "not-yet-created.sqlite"
    WorkOrderDatabaseAdapter(database_path)
    assert database_path.exists() is False


def test_finalization_failure_returns_framework_error(tmp_path) -> None:
    runner, _ = _runner(tmp_path, [PassingCase()])

    def fail_report(**kwargs):
        raise OSError("evidence unavailable")

    runner.evidence.write_report = fail_report
    assert runner.run() == 1
    assert runner.framework_status == "ERROR"



def test_evidence_bundle_serializes_sets_as_deterministic_arrays(tmp_path) -> None:
    bundle = EvidenceBundle(
        tmp_path,
        "ACCEPTANCE_SET_JSON",
        public_safe=False,
        redactor=Redactor(environment_values=[]),
    )
    bundle.write_json(
        "artifact.json",
        {
            "plain": {"beta", "alpha"},
            "nested": [{"values": frozenset({3, 1, 2})}],
        },
    )
    payload = json.loads((bundle.root / "artifact.json").read_text(encoding="utf-8"))
    assert payload["plain"] == ["alpha", "beta"]
    assert payload["nested"] == [{"values": [1, 2, 3]}]


def test_public_safe_evidence_bundle_serializes_and_redacts_sets(tmp_path) -> None:
    bundle = EvidenceBundle(
        tmp_path,
        "ACCEPTANCE_PUBLIC_SET_JSON",
        public_safe=True,
        redactor=Redactor(
            secrets=["secret-value"],
            environment_values=[],
        ),
    )
    bundle.write_json(
        "artifact.json",
        {"values": {"secret-value", "visible"}},
    )
    payload = json.loads((bundle.root / "artifact.json").read_text(encoding="utf-8"))
    assert payload["values"] == ["[REDACTED]", "visible"]
