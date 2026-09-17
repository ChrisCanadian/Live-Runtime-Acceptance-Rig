#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from live_runtime_rig_nexus_monster.cases import register_cases


PREFLIGHT_PLAN = (
    "Database adapter connection verified",
    "Database integrity check passed",
    "Database backup created and verified before writes",
    "Runtime adapter initialized",
    "Direct readiness probe passed",
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_run_root(evidence_root: Path) -> Path:
    candidates = [path.parent for path in evidence_root.glob("*/run.json") if path.is_file()]
    if not candidates:
        raise SystemExit(f"No completed rig run found beneath {evidence_root}")
    return max(candidates, key=lambda path: (path / "run.json").stat().st_mtime_ns)


def _blocked_by(checks: list[dict[str, Any]]) -> dict[str, Any] | None:
    for check in checks:
        if str(check.get("status", "")).upper() == "FAIL":
            return {
                "suite": str(check.get("suite", "UNKNOWN")),
                "name": str(check.get("name", "unknown failure")),
                "observed": check.get("observed"),
                "evidence_path": check.get("evidence_path"),
            }
    return None


def _case_executed(case: Any, run_root: Path, checks: list[dict[str, Any]]) -> bool:
    safe_name = str(case.name).replace("/", "_").replace("\\", "_")
    direct = run_root / "cases" / f"{safe_name}.json"
    if direct.is_file():
        return True
    return any(str(check.get("suite")) == str(case.suite) for check in checks)


def build_report(run_root: Path) -> dict[str, Any]:
    run = _load_json(run_root / "run.json")
    checks = list(run.get("checks") or [])
    observed_preflight = {
        str(check.get("name"))
        for check in checks
        if str(check.get("suite")) == "PREFLIGHT"
    }
    observed_suites = {str(check.get("suite")) for check in checks}

    not_run: list[dict[str, str]] = []
    for name in PREFLIGHT_PLAN:
        if name not in observed_preflight:
            not_run.append({"kind": "preflight", "suite": "PREFLIGHT", "name": name})

    for case in register_cases(None):
        if not _case_executed(case, run_root, checks):
            not_run.append({
                "kind": "case",
                "suite": str(case.suite),
                "name": str(case.name),
            })

    if "PROTECTED STATE" not in observed_suites:
        not_run.append({
            "kind": "postflight",
            "suite": "PROTECTED STATE",
            "name": "protected-state-unchanged",
        })

    report = {
        "schema_version": "1.0",
        "plan": "nexus-full-runtime-monster",
        "run_id": run.get("run_id"),
        "framework_status": run.get("framework_status"),
        "acceptance_status": run.get("acceptance_status"),
        "result_code": run.get("result_code"),
        "blocked_by": _blocked_by(checks),
        "not_run_count": len(not_run),
        "not_run": not_run,
    }
    (run_root / "not_run.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def print_report(report: dict[str, Any]) -> None:
    blocked = report.get("blocked_by")
    print()
    print("MONSTER CHAIN COMPLETION REPORT")
    print("-------------------------------")
    if blocked:
        print(f"Blocked by: {blocked['suite']} :: {blocked['name']}")
        print(f"Observed:   {blocked.get('observed')!r}")
        if blocked.get("evidence_path"):
            print(f"Evidence:   {blocked['evidence_path']}")
    else:
        print("Blocked by: none")

    items = list(report.get("not_run") or [])
    print(f"Not run:    {len(items)}")
    if items:
        print()
        print("MONSTER FLIGHT CONTROLS NOT COMPLETED")
        for item in items:
            print(f"  [NOT RUN] {item['suite']} :: {item['name']}")
    else:
        print("All planned monster flight-control stages were reached.")


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-root", type=Path)
    group.add_argument("--evidence-root", type=Path)
    args = parser.parse_args()

    run_root = (
        args.run_root.resolve()
        if args.run_root is not None
        else _latest_run_root(args.evidence_root.resolve())
    )
    if not (run_root / "run.json").is_file():
        raise SystemExit(f"run.json not found beneath {run_root}")
    report = build_report(run_root)
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
