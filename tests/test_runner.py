from __future__ import annotations

import io
import json
from pathlib import Path

from live_runtime_rig.config import RigConfig
from live_runtime_rig.console import Console
from live_runtime_rig.evidence import EvidenceBundle
from live_runtime_rig.runner import RigRunner, RunnerOptions
from live_runtime_rig_examples.fastapi_sqlite.cases import (
    IntentionalFailureCase,
    register_cases,
)
from live_runtime_rig_examples.fastapi_sqlite.database import initialize_database
from live_runtime_rig_examples.fastapi_sqlite.database_adapter import (
    create_database_adapter,
)
from live_runtime_rig_examples.fastapi_sqlite.runtime_adapter import (
    create_runtime_adapter,
)


def _config(tmp_path: Path, *, intentional_failure: bool = False) -> RigConfig:
    config_file = tmp_path / ".env"
    initialize_database(tmp_path / "work_orders.sqlite")
    config_file.write_text("# test config\n", encoding="utf-8")
    return RigConfig(
        config_file=config_file,
        runtime_adapter="unused:runtime",
        database_adapter="unused:database",
        cases="unused:cases",
        database_path=tmp_path / "work_orders.sqlite",
        evidence_dir=tmp_path / "evidence",
        application_label="test-work-orders",
        public_safe=True,
        intentional_failure=intentional_failure,
    )


def test_complete_toy_campaign_passes_and_compares_protected_state(tmp_path) -> None:
    config = _config(tmp_path)
    stream = io.StringIO()
    runner = RigRunner(
        config,
        run_id="ACCEPTANCE_PASS_TEST",
        runtime_factory=create_runtime_adapter,
        database_factory=create_database_adapter,
        case_loader=register_cases,
        console=Console(stream=stream),
    )
    code = runner.run()
    run = json.loads(
        (runner.evidence.root / "run.json").read_text(encoding="utf-8")
    )
    cleanup = json.loads(
        (runner.evidence.root / "cleanup_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert run["framework_status"] == "COMPLETED"
    assert run["acceptance_status"] == "PASS"
    assert run["summary"]["failed"] == 0
    assert run["summary"]["skipped"] == 1
    assert any(
        check["name"] == "Protected state remained unchanged"
        and check["status"] == "PASS"
        for check in run["checks"]
    )
    before = json.loads((runner.evidence.root / "database_before.json").read_text(encoding="utf-8"))
    assert before["protected_state_baseline"] == "post_runtime_initialization"
    assert len(cleanup["entries"]) == 7
    assert cleanup["automatic_cleanup_performed"] is False


def test_failed_acceptance_exits_one_without_framework_crash(tmp_path) -> None:
    config = _config(tmp_path, intentional_failure=True)
    runner = RigRunner(
        config,
        run_id="ACCEPTANCE_FAIL_TEST",
        runtime_factory=create_runtime_adapter,
        database_factory=create_database_adapter,
        case_loader=lambda _: [IntentionalFailureCase()],
        console=Console(quiet=True, stream=io.StringIO()),
    )
    code = runner.run()
    run = json.loads(
        (runner.evidence.root / "run.json").read_text(encoding="utf-8")
    )

    assert code == 1
    assert run["framework_status"] == "COMPLETED"
    assert run["acceptance_status"] == "FAIL"
    assert run["summary"]["failed"] == 1
    assert (runner.evidence.root / "report.md").is_file()
    assert (runner.evidence.root / "trace.ndjson").is_file()


def test_early_database_failure_still_writes_complete_evidence(tmp_path) -> None:
    config = _config(tmp_path)

    def broken_database_factory(_):
        raise RuntimeError("database unavailable")

    runner = RigRunner(
        config,
        run_id="ACCEPTANCE_EARLY_FAILURE_TEST",
        runtime_factory=create_runtime_adapter,
        database_factory=broken_database_factory,
        case_loader=lambda _: [IntentionalFailureCase()],
        console=Console(quiet=True, stream=io.StringIO()),
    )
    code = runner.run()

    assert code == 1
    for name in EvidenceBundle.REQUIRED_FILES:
        assert (runner.evidence.root / name).exists(), name
    run = json.loads(
        (runner.evidence.root / "run.json").read_text(encoding="utf-8")
    )
    assert run["framework_status"] == "COMPLETED"
    assert run["acceptance_status"] == "FAIL"
    error = json.loads(
        (runner.evidence.root / "errors" / "database_preflight.json").read_text(
            encoding="utf-8"
        )
    )
    assert error["exception_type"] == "RuntimeError"
    assert error["message"] == "[REDACTED_ERROR_MESSAGE]"


def test_quiet_prints_only_final_summary(tmp_path) -> None:
    config = _config(tmp_path)
    stream = io.StringIO()
    runner = RigRunner(
        config,
        options=RunnerOptions(quiet=True, cleanup_manifest_only=True),
        run_id="ACCEPTANCE_QUIET_TEST",
        console=Console(quiet=True, stream=stream),
    )
    assert runner.run() == 0
    output = stream.getvalue()
    assert "FRAMEWORK: COMPLETED" in output
    assert "RESULT: PASS" in output
    assert "LIVE RUNTIME ACCEPTANCE RIG" not in output
    assert "[00/" not in output
    assert "[PASS]" not in output


def test_verbose_includes_check_diagnostics(tmp_path) -> None:
    config = _config(tmp_path)
    stream = io.StringIO()
    runner = RigRunner(
        config,
        options=RunnerOptions(verbose=True, cleanup_manifest_only=True),
        run_id="ACCEPTANCE_VERBOSE_TEST",
        console=Console(verbose=True, stream=stream),
    )
    assert runner.run() == 0
    output = stream.getvalue()
    assert "Expected:" in output
    assert "Observed:" in output
    assert "cleanup_manifest.json" in output
