#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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

_FRAME_RE = re.compile(r'^\s*File "([^"]+)", line (\d+), in (.+)$')
_RELEVANT_ROOTS = ("/rig/", "/ndka/", "/production/", "/v5/")


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


def _failure_diagnostic(
    run_root: Path,
    blocked: dict[str, Any] | None,
    *,
    public_safe: bool,
) -> dict[str, Any] | None:
    if public_safe or not blocked or not blocked.get("evidence_path"):
        return None
    evidence_path = run_root / str(blocked["evidence_path"])
    if not evidence_path.is_file():
        return None
    try:
        payload = _load_json(evidence_path)
    except (OSError, json.JSONDecodeError):
        return None

    traceback_text = str(payload.get("traceback") or "")
    frames: list[dict[str, Any]] = []
    for line in traceback_text.splitlines():
        match = _FRAME_RE.match(line)
        if not match:
            continue
        path, line_number, function = match.groups()
        if any(root in path for root in _RELEVANT_ROOTS):
            frames.append(
                {
                    "path": path,
                    "line": int(line_number),
                    "function": function,
                }
            )

    return {
        "exception_type": payload.get("exception_type"),
        "message": payload.get("message"),
        "relevant_frames": frames,
        "traceback": traceback_text or None,
    }


def _case_executed(case: Any, run_root: Path, checks: list[dict[str, Any]]) -> bool:
    safe_name = str(case.name).replace("/", "_").replace("\\", "_")
    direct = run_root / "cases" / f"{safe_name}.json"
    if direct.is_file():
        return True
    return any(str(check.get("suite")) == str(case.suite) for check in checks)


def build_report(run_root: Path, *, public_safe: bool = False) -> dict[str, Any]:
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

    blocked = _blocked_by(checks)
    report = {
        "schema_version": "1.1",
        "plan": "nexus-full-runtime-monster",
        "run_id": run.get("run_id"),
        "framework_status": run.get("framework_status"),
        "acceptance_status": run.get("acceptance_status"),
        "result_code": run.get("result_code"),
        "blocked_by": blocked,
        "failure_diagnostic": _failure_diagnostic(
            run_root,
            blocked,
            public_safe=public_safe,
        ),
        "not_run_count": len(not_run),
        "not_run": not_run,
    }
    (run_root / "not_run.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def print_report(report: dict[str, Any], *, public_safe: bool = False) -> None:
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

    diagnostic = report.get("failure_diagnostic")
    if diagnostic:
        print()
        print("LOCAL RUNTIME FAILURE DIAGNOSTIC")
        print("--------------------------------")
        print(f"Exception: {diagnostic.get('exception_type')}")
        print(f"Message:   {diagnostic.get('message')}")
        frames = list(diagnostic.get("relevant_frames") or [])
        if frames:
            print("Relevant application frames:")
            for frame in frames:
                print(
                    f"  {frame['path']}:{frame['line']} in {frame['function']}"
                )
        traceback_text = diagnostic.get("traceback")
        if traceback_text:
            print("Full traceback:")
            print(traceback_text.rstrip())
    elif public_safe and blocked:
        print("Diagnostic detail: REDACTED (public-safe mode)")

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
    parser.add_argument("--public-safe", action="store_true")
    args = parser.parse_args()

    run_root = (
        args.run_root.resolve()
        if args.run_root is not None
        else _latest_run_root(args.evidence_root.resolve())
    )
    if not (run_root / "run.json").is_file():
        raise SystemExit(f"run.json not found beneath {run_root}")
    report = build_report(run_root, public_safe=args.public_safe)
    print_report(report, public_safe=args.public_safe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
