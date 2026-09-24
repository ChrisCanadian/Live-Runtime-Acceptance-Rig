from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_report_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "report_nexus_kernelized_incomplete.py"
    spec = importlib.util.spec_from_file_location("nexus_incomplete_report", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_preflight_failure_lists_downstream_not_run_stages(tmp_path) -> None:
    module = _load_report_module()
    run_root = tmp_path / "ACCEPTANCE_CHAIN_BREAK"
    run_root.mkdir()
    (run_root / "run.json").write_text(
        json.dumps(
            {
                "run_id": "ACCEPTANCE_CHAIN_BREAK",
                "framework_status": "COMPLETED",
                "acceptance_status": "FAIL",
                "result_code": "ACCEPTANCE_CHECK_FAILED",
                "checks": [
                    {
                        "suite": "PREFLIGHT",
                        "name": "Database adapter connection verified",
                        "status": "PASS",
                        "observed": True,
                    },
                    {
                        "suite": "PREFLIGHT",
                        "name": "Database integrity check passed",
                        "status": "PASS",
                        "observed": "ok",
                    },
                    {
                        "suite": "PREFLIGHT",
                        "name": "Database backup created and verified before writes",
                        "status": "PASS",
                        "observed": {"verified": True},
                    },
                    {
                        "suite": "PREFLIGHT",
                        "name": "Runtime adapter initialized",
                        "status": "FAIL",
                        "observed": "ModuleNotFoundError",
                        "evidence_path": "errors/runtime_preflight.json",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    report = module.build_report(run_root)

    assert report["blocked_by"]["name"] == "Runtime adapter initialized"
    assert report["blocked_by"]["observed"] == "ModuleNotFoundError"
    assert report["not_run_count"] == 10
    not_run = {(item["suite"], item["name"]) for item in report["not_run"]}
    assert ("PREFLIGHT", "Direct readiness probe passed") in not_run
    assert ("KERNELIZED HOST", "kernelized-readiness") in not_run
    assert ("DISCORD AUTHORITY", "discord-first-contact-isolation") in not_run
    assert ("DISCORD GOVERNED TURN", "discord-governed-turn") in not_run
    assert ("DISCORD SHARED KERNELS", "discord-shared-commands") in not_run
    assert ("MEMORY CONTINUITY", "discord-multi-turn-canonical-session") in not_run
    assert ("USER ISOLATION", "discord-cross-user-isolation") in not_run
    assert ("TOOLS EVIDENCE LOOP", "governed-tool-loop") in not_run
    assert ("DEFERRED INTEGRATION", "explicit-deferred-edges") in not_run
    assert ("PROTECTED STATE", "protected-state-unchanged") in not_run
    assert (run_root / "not_run.json").is_file()
