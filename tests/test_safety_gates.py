from __future__ import annotations

import io
import json
from pathlib import Path

from live_runtime_rig_examples.fastapi_sqlite.database_adapter import create_database_adapter
from live_runtime_rig.config import RigConfig
from live_runtime_rig.console import Console
from live_runtime_rig.redaction import Redactor
from live_runtime_rig.runner import RigRunner


class UnhealthyRuntime:
    def start(self) -> None:
        pass

    def close(self) -> None:
        pass

    def health(self):
        return {"ready": False}

    def direct_readiness_probe(self):
        return {"ready": True}

    def list_capabilities(self):
        return ()

    def request(self, method: str, path: str, **kwargs):
        raise AssertionError("write case should not run after failed health")


class MarkerCase:
    name = "must_not_run"
    suite = "safety"

    def __init__(self, state: dict[str, bool]) -> None:
        self.state = state

    def run(self, runtime, database, context):
        self.state["ran"] = True
        raise AssertionError("case should have been skipped")


def _config(tmp_path: Path) -> RigConfig:
    config_file = tmp_path / ".env"
    config_file.write_text("# test\n", encoding="utf-8")
    return RigConfig(
        config_file=config_file,
        runtime_adapter="unused:runtime",
        database_adapter="unused:database",
        cases="unused:cases",
        database_path=tmp_path / "work_orders.sqlite",
        evidence_dir=tmp_path / "evidence",
        application_label="safety-test",
        public_safe=True,
    )


def test_failed_runtime_readiness_prevents_write_cases(tmp_path) -> None:
    state = {"ran": False}
    runner = RigRunner(
        _config(tmp_path),
        run_id="ACCEPTANCE_RUNTIME_GATE_TEST",
        runtime_factory=lambda _: UnhealthyRuntime(),
        database_factory=create_database_adapter,
        case_loader=lambda _: [MarkerCase(state)],
        console=Console(quiet=True, stream=io.StringIO()),
    )
    code = runner.run()
    result = json.loads(
        (runner.evidence.root / "run.json").read_text(encoding="utf-8")
    )
    assert code == 1
    assert state["ran"] is False
    assert any(
        check["name"] == "Acceptance write cases"
        and check["status"] == "SKIP"
        for check in result["checks"]
    )


def test_public_safe_redaction_removes_database_filenames() -> None:
    redactor = Redactor(environment_values=[])
    redacted = redactor.redact_text("backup=campaign.backup.sqlite")
    assert "campaign.backup.sqlite" not in redacted
    assert "[REDACTED_DATABASE_PATH]" in redacted
