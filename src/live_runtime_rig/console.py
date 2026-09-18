"""Concise terminal output for observable acceptance campaigns."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TextIO

from .assertions import Check


class Console:
    def __init__(
        self,
        *,
        quiet: bool = False,
        verbose: bool = False,
        stream: TextIO | None = None,
    ) -> None:
        if quiet and verbose:
            raise ValueError("quiet and verbose cannot both be enabled")
        self.quiet = quiet
        self.verbose = verbose
        self.stream = stream or sys.stdout

    def _line(self, text: str = "") -> None:
        print(text, file=self.stream, flush=True)

    def start(self, run_id: str, public_safe: bool) -> None:
        if self.quiet:
            return
        self._line("LIVE RUNTIME ACCEPTANCE RIG")
        self._line(f"Run: {run_id}")
        self._line(f"Mode: {'public-safe' if public_safe else 'local-diagnostic'}")

    def suite(self, index: int, total: int, name: str) -> None:
        if self.quiet:
            return
        self._line()
        self._line(f"[{index:02d}/{total:02d}] {name.upper()}")

    def check(self, check: Check) -> None:
        if self.quiet:
            return
        suffix = " (heuristic)" if check.heuristic else ""
        self._line(f"  [{check.status.value}] {check.name}{suffix}")
        if self.verbose:
            self._line(f"         Expected: {check.expected!r}")
            self._line(f"         Observed: {check.observed!r}")
            if check.evidence_path:
                self._line(f"         Evidence: {check.evidence_path}")

    def diagnostic(self, label: str, value: Any) -> None:
        if self.verbose and not self.quiet:
            self._line(f"  {label}: {value!r}")

    def final(
        self,
        *,
        framework_status: str,
        acceptance_status: str,
        summary: dict[str, int],
        evidence_path: Path | str,
    ) -> None:
        if not self.quiet:
            self._line()
        self._line(f"FRAMEWORK: {framework_status}")
        self._line(f"RESULT: {acceptance_status}")
        self._line(f"Passed: {summary['passed']}")
        self._line(f"Failed: {summary['failed']}")
        self._line(f"Skipped: {summary['skipped']}")
        self._line(f"Not run: {summary.get('not_run', 0)}")
        self._line(f"Evidence: {evidence_path}")
