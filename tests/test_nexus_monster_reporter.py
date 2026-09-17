from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_reporter():
    path = Path(__file__).parents[1] / "scripts" / "report_nexus_monster_incomplete.py"
    spec = importlib.util.spec_from_file_location("nexus_monster_reporter", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_failed_run(root: Path) -> None:
    (root / "errors").mkdir(parents=True)
    (root / "run.json").write_text(
        json.dumps(
            {
                "run_id": "TEST_MONSTER_FAILURE",
                "framework_status": "COMPLETED",
                "acceptance_status": "FAIL",
                "result_code": 1,
                "checks": [
                    {
                        "suite": "PREFLIGHT",
                        "name": "Runtime adapter initialized",
                        "status": "FAIL",
                        "observed": "FileNotFoundError",
                        "evidence_path": "errors/runtime_preflight.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "errors" / "runtime_preflight.json").write_text(
        json.dumps(
            {
                "exception_type": "FileNotFoundError",
                "message": "Database not found: /production/data/Nexus_Framework_ProdV2.db",
                "traceback": (
                    'Traceback (most recent call last):\n'
                    '  File "/rig/src/live_runtime_rig/runner.py", line 385, in _run_campaign\n'
                    '    self.runtime.start()\n'
                    '  File "/ndka/src/nexus_ndka/migration/production_checkout.py", line 96, in bind_production_database\n'
                    '    database = importlib.import_module("core.database")\n'
                    '  File "/production/core/database.py", line 54, in __init__\n'
                    '    raise FileNotFoundError(...)\n'
                    'FileNotFoundError: Database not found: /production/data/Nexus_Framework_ProdV2.db\n'
                ),
            }
        ),
        encoding="utf-8",
    )


def test_local_report_loads_exception_message_frames_and_traceback(tmp_path: Path) -> None:
    reporter = _load_reporter()
    _write_failed_run(tmp_path)

    report = reporter.build_report(tmp_path, public_safe=False)
    diagnostic = report["failure_diagnostic"]

    assert diagnostic["exception_type"] == "FileNotFoundError"
    assert diagnostic["message"] == "Database not found: /production/data/Nexus_Framework_ProdV2.db"
    assert [frame["function"] for frame in diagnostic["relevant_frames"]] == [
        "_run_campaign",
        "bind_production_database",
        "__init__",
    ]
    assert "/production/core/database.py" in diagnostic["traceback"]


def test_public_safe_report_does_not_copy_private_diagnostic(tmp_path: Path) -> None:
    reporter = _load_reporter()
    _write_failed_run(tmp_path)

    report = reporter.build_report(tmp_path, public_safe=True)

    assert report["failure_diagnostic"] is None
    persisted = json.loads((tmp_path / "not_run.json").read_text(encoding="utf-8"))
    assert persisted["failure_diagnostic"] is None
