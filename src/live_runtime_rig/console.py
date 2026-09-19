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

        # Normal terminal mode is a cockpit view: one line per successful
        # acceptance assertion. Detailed expected/observed values remain in
        # run.json/case evidence and are only expanded live with --verbose.
        if self.verbose:
            self._line(f"         Expected: {check.expected!r}")
            self._line(f"         Observed: {check.observed!r}")
            if check.evidence_path:
                self._line(f"         Evidence: {check.evidence_path}")
            return

        # Failures and explicit skips still surface enough information to act
        # immediately without requiring the operator to hunt for the artifact.
        if check.status.value in {"FAIL", "SKIP"}:
            label = "Observed" if check.status.value == "FAIL" else "Reason"
            self._line(f"         {label}: {check.observed!r}")
            if check.evidence_path:
                self._line(f"         Evidence: {check.evidence_path}")

    def initialization(
        self,
        *,
        health: dict[str, Any],
        startup_log_path: str | None,
    ) -> None:
        """Render a non-authoritative operator summary.

        Cockpit rendering must never participate in acceptance semantics. The
        runtime health payload remains the evidence source; malformed or evolving
        display-only fields degrade the summary instead of failing the campaign.
        """

        if self.quiet:
            return

        try:
            analysis_raw = health.get("analysis_probe") or {}
            provider_raw = health.get("provider_probe") or {}
            rag_raw = health.get("rag_probe") or {}
            analysis = analysis_raw if isinstance(analysis_raw, dict) else {}
            provider = provider_raw if isinstance(provider_raw, dict) else {}
            rag = rag_raw if isinstance(rag_raw, dict) else {}
            registered = tuple(health.get("registered") or health.get("present") or ())
            failed = tuple(health.get("failed_kernel_ids") or ())
            degraded = tuple(health.get("degraded_kernel_ids") or ())

            self._line()
            self._line("NEXUS RUNTIME INITIALIZATION")
            self._line("----------------------------")
            self._line(
                f"  Kernels:  {len(registered)}/17 registered"
                + (" / READY" if not failed and not degraded else "")
            )
            self._line(
                "  NLP:      "
                + (
                    "READY / full local production pipeline"
                    if analysis.get("status") == "ok"
                    else str(analysis.get("status") or "UNKNOWN").upper()
                )
            )
            if analysis.get("source"):
                self._line(f"            source={analysis.get('source')}")

            latency_breakdown = analysis.get("latency_breakdown")
            if isinstance(latency_breakdown, dict):
                details = []
                total = latency_breakdown.get("total_ms")
                stanza = latency_breakdown.get("stanza_ms")
                if isinstance(total, (int, float)):
                    details.append(f"total={float(total):.0f}ms")
                if isinstance(stanza, (int, float)):
                    details.append(f"stanza={float(stanza):.0f}ms")
                if details:
                    self._line(f"            {' / '.join(details)}")

            provider_id = provider.get("provider_id") or health.get("provider_id")
            model_id = provider.get("model_id") or health.get("model_id")
            self._line(
                "  Provider: "
                + (
                    f"READY / {provider_id} / {model_id}"
                    if (provider.get("status") == "ok" or health.get("real_provider"))
                    else "UNKNOWN"
                )
            )
            self._line(
                "  RAG:      "
                + (
                    f"READY / {rag.get('embedding_dimensions', '?')}d / "
                    f"{rag.get('conversation_vectors', '?')} vectors"
                    if rag.get("rag_initialized")
                    else "UNKNOWN"
                )
            )
            if startup_log_path:
                self._line(f"  Detail:   {startup_log_path}")
        except Exception as exc:
            # Presentation must never alter runtime/test outcome.
            self._line()
            self._line("NEXUS RUNTIME INITIALIZATION")
            self._line("----------------------------")
            self._line("  Summary:  unavailable (display-only formatting error)")
            if startup_log_path:
                self._line(f"  Detail:   {startup_log_path}")
            if self.verbose:
                self._line(f"  Display error: {type(exc).__name__}: {exc}")

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
