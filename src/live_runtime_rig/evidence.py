"""Evidence bundle creation that remains usable after early failures."""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .assertions import Check
from .redaction import Redactor


class EvidenceBundle:
    SUBDIRECTORIES = ("backups", "cases", "artifacts", "errors")
    REQUIRED_FILES = (
        "run.json",
        "report.md",
        "summary.txt",
        "trace.ndjson",
        "environment.json",
        "database_before.json",
        "database_after.json",
        "cleanup_manifest.json",
    )

    def __init__(
        self,
        base_directory: Path,
        run_id: str,
        *,
        public_safe: bool,
        redactor: Redactor,
    ) -> None:
        self.run_id = run_id
        self.public_safe = public_safe
        self.redactor = redactor
        self.root = base_directory / run_id
        self.root.mkdir(parents=True, exist_ok=False)
        for name in self.SUBDIRECTORIES:
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / "trace.ndjson").touch()

    @property
    def display_path(self) -> str:
        if self.public_safe:
            return (Path(self.root.parent.name) / self.root.name).as_posix()
        return str(self.root)

    def _safe(self, value: Any) -> Any:
        return self.redactor.redact_value(value) if self.public_safe else value

    def write_json(self, relative_path: str, payload: Any) -> str:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        safe_payload = self._safe(payload)
        path.write_text(
            json.dumps(
                safe_payload,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
        return relative_path.replace("\\", "/")

    def write_text(self, relative_path: str, text: str) -> str:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        safe_text = self.redactor.redact_text(text) if self.public_safe else text
        path.write_text(safe_text, encoding="utf-8")
        return relative_path.replace("\\", "/")

    def write_case(self, case_name: str, payload: Mapping[str, Any]) -> str:
        safe_name = "".join(
            char if char.isalnum() or char in {"-", "_"} else "_"
            for char in case_name
        )
        return self.write_json(f"cases/{safe_name}.json", payload)

    def write_error(self, label: str, exc: BaseException) -> str:
        safe_name = "".join(
            char if char.isalnum() or char in {"-", "_"} else "_"
            for char in label
        )
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "exception_type": type(exc).__name__,
        }
        if self.public_safe:
            payload["message"] = "[REDACTED_ERROR_MESSAGE]"
            payload["traceback"] = "[OMITTED_IN_PUBLIC_SAFE_MODE]"
        else:
            payload["message"] = str(exc)
            payload["traceback"] = traceback.format_exc()
        return self.write_json(f"errors/{safe_name}.json", payload)

    def ensure_required_files(self) -> None:
        defaults: dict[str, Any] = {
            "run.json": {},
            "report.md": "# Acceptance report\n",
            "summary.txt": "No summary was available.\n",
            "environment.json": {},
            "database_before.json": {"available": False},
            "database_after.json": {"available": False},
            "cleanup_manifest.json": {
                "run_id": self.run_id,
                "automatic_cleanup_performed": False,
                "entries": [],
            },
        }
        for name in self.REQUIRED_FILES:
            path = self.root / name
            if path.exists():
                continue
            if name == "trace.ndjson":
                path.touch()
            elif name.endswith(".json"):
                self.write_json(name, defaults[name])
            else:
                self.write_text(name, str(defaults[name]))

    def write_report(
        self,
        *,
        framework_status: str,
        acceptance_status: str,
        checks: tuple[Check, ...],
        summary: Mapping[str, int],
    ) -> None:
        lines = [
            "# Live runtime acceptance report",
            "",
            f"- Run: `{self.run_id}`",
            f"- Framework execution: **{framework_status}**",
            f"- Acceptance result: **{acceptance_status}**",
            (
                f"- Checks: {summary['total']} total, {summary['passed']} passed, "
                f"{summary['failed']} failed, {summary['skipped']} skipped"
            ),
            "",
            "> A run with one failed acceptance check can still represent a successful "
            "test campaign if the framework correctly detected, preserved, and reported "
            "a real defect.",
            "",
            "## Checks",
            "",
            "| Suite | Status | Check | Heuristic | Evidence |",
            "|---|---:|---|---:|---|",
        ]
        for check in checks:
            lines.append(
                "| "
                + " | ".join(
                    (
                        check.suite.replace("|", "\\|"),
                        check.status.value,
                        check.name.replace("|", "\\|"),
                        "yes" if check.heuristic else "no",
                        (check.evidence_path or "").replace("|", "\\|"),
                    )
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "## Evidence",
                "",
                "- `run.json`: detailed machine-readable result",
                "- `trace.ndjson`: ordered process-local events",
                "- `database_before.json` and `database_after.json`: durable snapshots",
                "- `cleanup_manifest.json`: current-run resources only",
                "- `cases/`: per-case request and readback receipts",
                "",
            ]
        )
        self.write_text("report.md", "\n".join(lines))
        summary_text = (
            f"LIVE RUNTIME ACCEPTANCE - {acceptance_status}\n"
            f"Framework: {framework_status}\n"
            f"Run: {self.run_id}\n"
            f"Passed: {summary['passed']}\n"
            f"Failed: {summary['failed']}\n"
            f"Skipped: {summary['skipped']}\n"
            f"Evidence: {self.display_path}\n"
        )
        self.write_text("summary.txt", summary_text)
