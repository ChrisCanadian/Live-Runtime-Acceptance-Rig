"""Acceptance campaign orchestration."""

from __future__ import annotations

import importlib
import platform
import secrets
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .assertions import AssertionLedger, CheckStatus
from .cleanup import CleanupManifest
from .config import RigConfig
from .console import Console
from .contracts import AcceptanceCase, CaseContext, CaseResult, CheckSpec
from .evidence import EvidenceBundle
from .redaction import Redactor
from .tracer import Tracer


@dataclass(frozen=True)
class RunnerOptions:
    quiet: bool = False
    verbose: bool = False
    case: str | None = None
    public_safe: bool = False
    cleanup_manifest_only: bool = False


def generate_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"ACCEPTANCE_{timestamp}_{secrets.token_hex(2).upper()}"


def load_symbol(specification: str) -> Any:
    if ":" not in specification:
        raise ValueError("Adapter and case references must use module:symbol")
    module_name, symbol_name = specification.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, symbol_name)


class RigRunner:
    """Runs a campaign while keeping execution and acceptance statuses separate."""

    def __init__(
        self,
        config: RigConfig,
        *,
        options: RunnerOptions | None = None,
        run_id: str | None = None,
        runtime_factory: Callable[[RigConfig], Any] | None = None,
        database_factory: Callable[[RigConfig], Any] | None = None,
        case_loader: Callable[[RigConfig], Iterable[AcceptanceCase]] | None = None,
        console: Console | None = None,
    ) -> None:
        self.config = config
        self.options = options or RunnerOptions()
        self.run_id = run_id or generate_run_id()
        self.marker = self.run_id
        self.public_safe = self.options.public_safe or config.public_safe
        self.redactor = Redactor()
        self.evidence = EvidenceBundle(
            config.evidence_dir,
            self.run_id,
            public_safe=self.public_safe,
            redactor=self.redactor,
        )
        self.tracer = Tracer(
            self.evidence.root / "trace.ndjson",
            self.run_id,
            redactor=self.redactor if self.public_safe else Redactor(environment_values=()),
        )
        self.ledger = AssertionLedger()
        self.cleanup = CleanupManifest(self.run_id, self.marker)
        self.console = console or Console(
            quiet=self.options.quiet,
            verbose=self.options.verbose,
        )
        self.runtime_factory = runtime_factory
        self.database_factory = database_factory
        self.case_loader = case_loader
        self.runtime: Any = None
        self.database: Any = None
        self.framework_status = "COMPLETED"
        self.started_at = datetime.now(timezone.utc)
        self._started_clock = time.perf_counter()

    def _record(
        self,
        *,
        suite: str,
        name: str,
        status: CheckStatus,
        expected: Any,
        observed: Any,
        evidence_path: str | None = None,
        heuristic: bool = False,
    ) -> None:
        safe_expected = (
            self.redactor.redact_value(expected) if self.public_safe else expected
        )
        safe_observed = (
            self.redactor.redact_value(observed) if self.public_safe else observed
        )
        check = self.ledger.record(
            suite=suite,
            name=name,
            status=status,
            expected=safe_expected,
            observed=safe_observed,
            evidence_path=evidence_path,
            heuristic=heuristic,
        )
        self.console.check(check)

    def _record_spec(
        self,
        suite: str,
        specification: CheckSpec,
        *,
        default_evidence: str,
    ) -> None:
        self._record(
            suite=suite,
            name=specification.name,
            status=specification.status,
            expected=specification.expected,
            observed=specification.observed,
            evidence_path=specification.evidence_path or default_evidence,
            heuristic=specification.heuristic,
        )

    def _environment(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "generated_at": self.started_at.isoformat(),
            "python": platform.python_version(),
            "platform": sys.platform,
            "application_label": self.config.application_label,
            "public_safe": self.public_safe,
            "config_file": self.config.config_file.name,
            "database_path": (
                "[REDACTED_DATABASE_PATH]"
                if self.public_safe
                else str(self.config.database_path)
            ),
            "network_required": False,
        }

    def _resolve_components(self) -> tuple[Callable[..., Any], Callable[..., Any], Callable[..., Any]]:
        runtime_factory = self.runtime_factory or load_symbol(
            self.config.runtime_adapter
        )
        database_factory = self.database_factory or load_symbol(
            self.config.database_adapter
        )
        case_loader = self.case_loader or load_symbol(self.config.cases)
        return runtime_factory, database_factory, case_loader

    def _run_manifest_only(self) -> None:
        self.console.suite(0, 0, "cleanup manifest")
        path = self.evidence.write_json(
            "cleanup_manifest.json", self.cleanup.as_dict()
        )
        self._record(
            suite="CLEANUP MANIFEST",
            name="Empty current-run cleanup manifest generated",
            status=CheckStatus.PASS,
            expected=0,
            observed=0,
            evidence_path=path,
        )
        self.evidence.write_json(
            "database_before.json",
            {"available": False, "reason": "cleanup-manifest-only mode"},
        )
        self.evidence.write_json(
            "database_after.json",
            {"available": False, "reason": "cleanup-manifest-only mode"},
        )

    def _run_campaign(self) -> None:
        runtime_factory, database_factory, case_loader = self._resolve_components()
        cases = list(case_loader(self.config))
        if self.options.case:
            requested = self.options.case.casefold()
            cases = [
                case
                for case in cases
                if case.name.casefold() == requested
                or case.suite.casefold() == requested
            ]
            if not cases:
                self.console.suite(0, 1, "case selection")
                self._record(
                    suite="CASE SELECTION",
                    name="Requested case or suite exists",
                    status=CheckStatus.FAIL,
                    expected=self.options.case,
                    observed="no match",
                )
                return

        total_suites = 2 + len({case.suite for case in cases})
        self.console.suite(0, total_suites, "preflight")
        preflight_failed = False

        try:
            self.database = database_factory(self.config)
            connection = self.database.verify_connection()
            connected = connection.get("connected") is True
            self._record(
                suite="PREFLIGHT",
                name="Database adapter connection verified",
                status=CheckStatus.PASS if connected else CheckStatus.FAIL,
                expected=True,
                observed=connection.get("connected"),
            )
            preflight_failed = preflight_failed or not connected

            integrity = self.database.integrity_check()
            integrity_ok = integrity.get("result") == "ok"
            self._record(
                suite="PREFLIGHT",
                name="Database integrity check passed",
                status=CheckStatus.PASS if integrity_ok else CheckStatus.FAIL,
                expected="ok",
                observed=integrity.get("result"),
            )
            preflight_failed = preflight_failed or not integrity_ok

            before = dict(self.database.snapshot_state())
            protected_before = dict(self.database.protected_state_snapshot())
            before_payload = {
                "available": True,
                "state": before,
                "protected_state": protected_before,
            }
            self.evidence.write_json("database_before.json", before_payload)

            backup_destination = (
                self.evidence.root / "backups" / f"{self.run_id}.backup.sqlite"
            )
            backup = dict(self.database.backup(backup_destination))
            backup_ok = (
                backup.get("verified") is True
                and backup.get("integrity") == "ok"
                and isinstance(backup.get("size_bytes"), int)
                and int(backup["size_bytes"]) > 0
                and isinstance(backup.get("sha256"), str)
                and len(str(backup["sha256"])) == 64
            )
            backup_evidence = self.evidence.write_json("backups/backup.json", backup)
            self._record(
                suite="PREFLIGHT",
                name="Database backup created and verified before writes",
                status=CheckStatus.PASS if backup_ok else CheckStatus.FAIL,
                expected={
                    "verified": True,
                    "integrity": "ok",
                    "sha256_length": 64,
                },
                observed={
                    "verified": backup.get("verified"),
                    "integrity": backup.get("integrity"),
                    "sha256_length": len(str(backup.get("sha256", ""))),
                },
                evidence_path=backup_evidence,
            )
            preflight_failed = preflight_failed or not backup_ok
        except Exception as exc:
            error_path = self.evidence.write_error("database_preflight", exc)
            self._record(
                suite="PREFLIGHT",
                name="Database preflight completed",
                status=CheckStatus.FAIL,
                expected="verified connection, integrity, snapshot, and backup",
                observed=type(exc).__name__,
                evidence_path=error_path,
            )
            preflight_failed = True
            protected_before = {}

        if preflight_failed:
            self._record(
                suite="PREFLIGHT",
                name="Runtime start and write cases",
                status=CheckStatus.SKIP,
                expected="verified backup before writes",
                observed="skipped after preflight failure",
            )
            return

        try:
            self.runtime = runtime_factory(self.config)
            self.runtime.start()
            health = self.runtime.health()
            healthy = health.get("ready") is True
            self._record(
                suite="PREFLIGHT",
                name="Runtime adapter initialized",
                status=CheckStatus.PASS if healthy else CheckStatus.FAIL,
                expected=True,
                observed=health.get("ready"),
            )
            readiness = self.runtime.direct_readiness_probe()
            ready = readiness.get("ready") is True
            self._record(
                suite="PREFLIGHT",
                name="Direct readiness probe passed",
                status=CheckStatus.PASS if ready else CheckStatus.FAIL,
                expected=True,
                observed=readiness.get("ready"),
            )
            capabilities = list(self.runtime.list_capabilities())
            self.evidence.write_json(
                "artifacts/capabilities.json", {"capabilities": capabilities}
            )
            if not healthy or not ready:
                self._record(
                    suite="PREFLIGHT",
                    name="Acceptance write cases",
                    status=CheckStatus.SKIP,
                    expected="healthy and ready runtime",
                    observed="skipped after runtime preflight failure",
                )
                return
        except Exception as exc:
            error_path = self.evidence.write_error("runtime_preflight", exc)
            self._record(
                suite="PREFLIGHT",
                name="Runtime adapter initialized",
                status=CheckStatus.FAIL,
                expected="ready runtime boundary",
                observed=type(exc).__name__,
                evidence_path=error_path,
            )
            return

        state: dict[str, Any] = {}
        context = CaseContext(
            run_id=self.run_id,
            marker=self.marker,
            public_safe=self.public_safe,
            settings=self.config.case_settings(),
            evidence=self.evidence,
            tracer=self.tracer,
            state=state,
        )
        ordered_suites: list[str] = []
        for case in cases:
            if case.suite not in ordered_suites:
                ordered_suites.append(case.suite)
        suite_index = 1
        for suite in ordered_suites:
            self.console.suite(suite_index, total_suites, suite)
            suite_index += 1
            for case in (item for item in cases if item.suite == suite):
                with self.tracer.span(
                    "case.execution", suite=case.suite, case=case.name
                ):
                    try:
                        result = case.run(self.runtime, self.database, context)
                        if not isinstance(result, CaseResult):
                            raise TypeError("case must return CaseResult")
                        case_path = self.evidence.write_case(
                            case.name,
                            {
                                "case": case.name,
                                "suite": case.suite,
                                "evidence": result.evidence,
                                "cleanup_entry_count": len(result.cleanup_entries),
                            },
                        )
                        for specification in result.checks:
                            self._record_spec(
                                case.suite,
                                specification,
                                default_evidence=case_path,
                            )
                        for entry in result.cleanup_entries:
                            self.cleanup.add(entry)
                        state.update(result.state_updates)
                    except Exception as exc:
                        error_path = self.evidence.write_error(
                            f"case_{case.name}", exc
                        )
                        self._record(
                            suite=case.suite,
                            name=f"{case.name} completed without framework exception",
                            status=CheckStatus.FAIL,
                            expected="CaseResult",
                            observed=type(exc).__name__,
                            evidence_path=error_path,
                        )

        self.console.suite(total_suites - 1, total_suites, "protected state")
        try:
            protected_after = dict(self.database.protected_state_snapshot())
            after = dict(self.database.snapshot_state())
            self.evidence.write_json(
                "database_after.json",
                {
                    "available": True,
                    "state": after,
                    "protected_state": protected_after,
                },
            )
            unchanged = protected_after == protected_before
            self._record(
                suite="PROTECTED STATE",
                name="Protected state remained unchanged",
                status=CheckStatus.PASS if unchanged else CheckStatus.FAIL,
                expected=protected_before,
                observed=protected_after,
                evidence_path="database_after.json",
            )
        except Exception as exc:
            error_path = self.evidence.write_error("database_after", exc)
            self._record(
                suite="PROTECTED STATE",
                name="Protected state comparison completed",
                status=CheckStatus.FAIL,
                expected="before/after comparison",
                observed=type(exc).__name__,
                evidence_path=error_path,
            )

    def _finalize(self) -> int:
        self.evidence.write_json("cleanup_manifest.json", self.cleanup.as_dict())
        self.evidence.ensure_required_files()
        summary = self.ledger.summary()
        acceptance_status = "FAIL" if self.ledger.failed else "PASS"
        completed_at = datetime.now(timezone.utc)
        run_payload = {
            "run_id": self.run_id,
            "framework_status": self.framework_status,
            "acceptance_status": acceptance_status,
            "started_at": self.started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "elapsed_seconds": round(time.perf_counter() - self._started_clock, 3),
            "public_safe": self.public_safe,
            "application_label": self.config.application_label,
            "summary": summary,
            "checks": [check.as_dict() for check in self.ledger.checks],
            "cleanup_manifest": "cleanup_manifest.json",
        }
        self.evidence.write_json("run.json", run_payload)
        self.evidence.write_report(
            framework_status=self.framework_status,
            acceptance_status=acceptance_status,
            checks=self.ledger.checks,
            summary=summary,
        )
        self.console.final(
            framework_status=self.framework_status,
            acceptance_status=acceptance_status,
            summary=summary,
            evidence_path=self.evidence.display_path,
        )
        return (
            0
            if self.framework_status == "COMPLETED" and acceptance_status == "PASS"
            else 1
        )

    def run(self) -> int:
        self.console.start(self.run_id, self.public_safe)
        self.evidence.write_json("environment.json", self._environment())
        self.tracer.emit(
            "campaign.execution",
            phase="started",
            public_safe=self.public_safe,
        )
        try:
            if self.options.cleanup_manifest_only:
                self._run_manifest_only()
            else:
                self._run_campaign()
        except Exception as exc:
            self.framework_status = "ERROR"
            error_path = self.evidence.write_error("framework", exc)
            self._record(
                suite="FRAMEWORK",
                name="Framework execution completed",
                status=CheckStatus.FAIL,
                expected="completed",
                observed=type(exc).__name__,
                evidence_path=error_path,
            )
        finally:
            if self.runtime is not None:
                try:
                    self.runtime.close()
                except Exception as exc:
                    error_path = self.evidence.write_error("runtime_close", exc)
                    self._record(
                        suite="FRAMEWORK",
                        name="Runtime adapter closed",
                        status=CheckStatus.FAIL,
                        expected="closed",
                        observed=type(exc).__name__,
                        evidence_path=error_path,
                    )
            self.tracer.emit(
                "campaign.execution",
                phase="completed",
                framework_status=self.framework_status,
                acceptance_failed=self.ledger.failed,
                elapsed_ms=round(
                    (time.perf_counter() - self._started_clock) * 1000, 3
                ),
            )
        return self._finalize()
