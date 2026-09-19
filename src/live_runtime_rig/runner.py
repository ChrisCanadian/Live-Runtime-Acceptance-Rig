"""Acceptance campaign orchestration."""

from __future__ import annotations

import contextlib
import importlib
import io
import platform
import secrets
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .assertions import AssertionLedger, CheckStatus
from .backup import BackupProofError, verify_backup_proof
from .cleanup import CleanupManifest
from .config import RigConfig
from .console import Console
from .contracts import (
    AcceptanceCase,
    BackupProof,
    CaseContext,
    CaseResult,
    CheckSpec,
)
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
        self._executed_acceptance_checks = 0
        self._planned_cases: tuple[tuple[str, str], ...] = ()
        self._planned_check_keys: tuple[tuple[str, str], ...] = ()
        self._fallback_planned_cases: tuple[tuple[str, str], ...] = ()
        self._executed_cases: set[tuple[str, str]] = set()
        self._result_code = "PASS"

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

    def _register_cleanup_entries(self, entries: Iterable[Any]) -> None:
        self.cleanup.add_many(entries)
        self.evidence.write_json("cleanup_manifest.json", self.cleanup.as_dict())

    def _write_runtime_log(
        self,
        relative: Path,
        *,
        stdout_text: str,
        stderr_text: str,
    ) -> str | None:
        """Persist noisy application/library output without flooding the cockpit."""

        if not stdout_text and not stderr_text:
            return None

        parts: list[str] = []
        if stdout_text:
            parts.extend(("=== STDOUT ===", stdout_text.rstrip(), ""))
        if stderr_text:
            parts.extend(("=== STDERR ===", stderr_text.rstrip(), ""))
        payload = "\n".join(parts).rstrip() + "\n"
        if self.public_safe:
            payload = self.redactor.redact_text(payload)

        destination = self.evidence.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload, encoding="utf-8")
        return relative.as_posix()

    def _write_case_runtime_log(
        self,
        case_name: str,
        *,
        stdout_text: str,
        stderr_text: str,
    ) -> str | None:
        safe_name = self.evidence.safe_case_name(case_name)
        return self._write_runtime_log(
            Path("logs") / "cases" / f"{safe_name}.log",
            stdout_text=stdout_text,
            stderr_text=stderr_text,
        )

    def _environment(self) -> dict[str, Any]:
        provenance = {
            key: value
            for key, value in self.config.provenance.items()
        } or {
            key: "programmatic"
            for key in (
                "RIG_RUNTIME_ADAPTER",
                "RIG_DATABASE_ADAPTER",
                "RIG_CASES",
                "RIG_DATABASE_PATH",
                "RIG_EVIDENCE_DIR",
                "RIG_APPLICATION_LABEL",
                "RIG_PUBLIC_SAFE",
                "RIG_INTENTIONAL_FAILURE",
                "RIG_NETWORK_REQUIRED",
            )
        }
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
            "network_required": self.config.network_required,
            "configuration_provenance": provenance,
            "runner_option_provenance": {
                "public_safe": (
                    "CLI" if self.options.public_safe else provenance["RIG_PUBLIC_SAFE"]
                ),
                "case": "CLI" if self.options.case else "default",
                "cleanup_manifest_only": (
                    "CLI" if self.options.cleanup_manifest_only else "default"
                ),
            },
            "environment_overrides_enabled": (
                self.config.environment_overrides_enabled
            ),
            "ignored_environment_overrides": list(
                self.config.ignored_environment_overrides
            ),
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
                self._result_code = "CASE_SELECTION_NOT_FOUND"
                return

        if not cases:
            self._result_code = "NO_EXECUTED_ACCEPTANCE_CHECKS"
            return

        self._planned_cases = tuple((case.suite, case.name) for case in cases)
        planned_check_keys: list[tuple[str, str]] = []
        fallback_planned_cases: list[tuple[str, str]] = []
        for case in cases:
            declared = tuple(getattr(case, "planned_checks", ()) or ())
            if declared:
                planned_check_keys.extend((case.suite, str(name)) for name in declared)
            else:
                # Generic/application-neutral cases may not expose check-level
                # planning metadata. Preserve their historical case-level
                # accounting instead of inventing names that can never appear
                # in the assertion ledger.
                fallback_planned_cases.append((case.suite, case.name))
        self._planned_check_keys = tuple(planned_check_keys)
        self._fallback_planned_cases = tuple(fallback_planned_cases)

        evidence_names: dict[str, str] = {}
        for case in cases:
            safe_name = self.evidence.safe_case_name(case.name).casefold()
            previous = evidence_names.get(safe_name)
            if previous is not None:
                self._record(
                    suite="CASE SELECTION",
                    name="Case evidence names are unique",
                    status=CheckStatus.FAIL,
                    expected="unique sanitized case names",
                    observed={"first": previous, "second": case.name},
                )
                self._result_code = "DUPLICATE_CASE_EVIDENCE_NAME"
                return
            evidence_names[safe_name] = case.name

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
            protected_before = {}
            before_payload = {
                "available": True,
                "state": before,
                "protected_state": None,
                "protected_state_baseline": "pending_runtime_initialization",
            }
            self.evidence.write_json("database_before.json", before_payload)

            backup_destination = (
                self.evidence.root / "backups" / f"{self.run_id}.backup.sqlite"
            )
            proof = self.database.backup(backup_destination)
            verification = None
            backup_code = "VERIFIED"
            try:
                verification = verify_backup_proof(
                    proof,
                    expected_destination=backup_destination,
                    database=self.database,
                )
                backup_ok = True
            except BackupProofError as exc:
                backup_ok = False
                backup_code = exc.code
            proof_payload = (
                proof.as_dict()
                if isinstance(proof, BackupProof)
                else {"reported_type": type(proof).__name__}
            )
            backup_evidence = self.evidence.write_json(
                "backups/backup.json",
                {
                    "proof": proof_payload,
                    "verification": (
                        verification.as_dict() if verification is not None else None
                    ),
                    "result_code": backup_code,
                },
            )
            self._record(
                suite="PREFLIGHT",
                name="Database backup created and verified before writes",
                status=CheckStatus.PASS if backup_ok else CheckStatus.FAIL,
                expected={
                    "verified": True,
                    "integrity": "ok",
                    "file_matches_reported_size_and_sha256": True,
                },
                observed={
                    "verified": backup_ok,
                    "result_code": backup_code,
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
            startup_stdout = io.StringIO()
            startup_stderr = io.StringIO()
            if self.options.verbose:
                self.runtime.start()
                startup_log_path = None
            else:
                with contextlib.redirect_stdout(startup_stdout), contextlib.redirect_stderr(startup_stderr):
                    self.runtime.start()
                startup_log_path = self._write_runtime_log(
                    Path("logs") / "runtime-start.log",
                    stdout_text=startup_stdout.getvalue(),
                    stderr_text=startup_stderr.getvalue(),
                )
            # Runtime construction may migrate or seed its own disposable state.
            # Protected-state comparison begins only after that normal setup is
            # complete, before the campaign is allowed to issue write cases.
            protected_before = dict(self.database.protected_state_snapshot())
            self.evidence.write_json(
                "database_before.json",
                {
                    "available": True,
                    "state": before,
                    "protected_state": protected_before,
                    "protected_state_baseline": "post_runtime_initialization",
                },
            )
            health = self.runtime.health()
            healthy = health.get("ready") is True
            if not self.options.verbose and not self.options.quiet:
                self.console.initialization(
                    health=health,
                    startup_log_path=startup_log_path,
                )
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
            if not self.options.verbose:
                try:
                    self._write_runtime_log(
                        Path("logs") / "runtime-start.log",
                        stdout_text=locals().get("startup_stdout", io.StringIO()).getvalue(),
                        stderr_text=locals().get("startup_stderr", io.StringIO()).getvalue(),
                    )
                except Exception:
                    pass
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
            _cleanup_registrar=self._register_cleanup_entries,
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
                self._executed_cases.add((case.suite, case.name))
                captured_stdout = io.StringIO()
                captured_stderr = io.StringIO()
                runtime_log_path: str | None = None
                try:
                    with self.tracer.span(
                        "case.execution", suite=case.suite, case=case.name
                    ):
                        if self.options.verbose:
                            result = case.run(self.runtime, self.database, context)
                        else:
                            # Keep the normal terminal human-readable while
                            # retaining subsystem chatter and library diagnostics
                            # as evidence. --verbose restores the historical live
                            # firehose for deep debugging.
                            with contextlib.redirect_stdout(captured_stdout), contextlib.redirect_stderr(captured_stderr):
                                result = case.run(self.runtime, self.database, context)
                            runtime_log_path = self._write_case_runtime_log(
                                case.name,
                                stdout_text=captured_stdout.getvalue(),
                                stderr_text=captured_stderr.getvalue(),
                            )
                        if not isinstance(result, CaseResult):
                            raise TypeError("case must return CaseResult")
                        case_path = self.evidence.write_case(
                            case.name,
                            {
                                "case": case.name,
                                "suite": case.suite,
                                "evidence": result.evidence,
                                "cleanup_entry_count": len(result.cleanup_entries),
                                "runtime_log": runtime_log_path,
                            },
                        )
                        for specification in result.checks:
                            self._record_spec(
                                case.suite,
                                specification,
                                default_evidence=case_path,
                            )
                            if specification.status is not CheckStatus.SKIP:
                                self._executed_acceptance_checks += 1
                        self._register_cleanup_entries(result.cleanup_entries)
                        state.update(result.state_updates)
                except Exception as exc:
                    if not self.options.verbose:
                        runtime_log_path = self._write_case_runtime_log(
                            case.name,
                            stdout_text=captured_stdout.getvalue(),
                            stderr_text=captured_stderr.getvalue(),
                        )
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


    def _not_run_checks(self) -> list[dict[str, str]]:
        """Return individual planned checks that were never reached.

        NOT RUN is a third axis, separate from FAIL and SKIP. A failed check was
        executed and therefore is not NOT RUN. A skipped check was explicitly
        evaluated as SKIP and therefore is also not NOT RUN.
        """

        if self.options.cleanup_manifest_only:
            return []

        observed = {(check.suite, check.name) for check in self.ledger.checks}
        not_run: list[dict[str, str]] = []

        preflight_plan = (
            "Database adapter connection verified",
            "Database integrity check passed",
            "Database backup created and verified before writes",
            "Runtime adapter initialized",
            "Direct readiness probe passed",
        )
        for name in preflight_plan:
            key = ("PREFLIGHT", name)
            if key not in observed:
                not_run.append({"kind": "preflight", "suite": key[0], "name": key[1]})

        for suite, name in self._planned_check_keys:
            if (suite, name) not in observed:
                not_run.append({"kind": "acceptance_check", "suite": suite, "name": name})

        for suite, case_name in self._fallback_planned_cases:
            if (suite, case_name) not in self._executed_cases:
                not_run.append(
                    {"kind": "acceptance_case", "suite": suite, "name": case_name}
                )

        protected_key = ("PROTECTED STATE", "Protected state remained unchanged")
        protected_fallback = ("PROTECTED STATE", "Protected state comparison completed")
        if self._planned_cases and protected_key not in observed and protected_fallback not in observed:
            not_run.append(
                {
                    "kind": "postflight",
                    "suite": "PROTECTED STATE",
                    "name": "Protected state remained unchanged",
                }
            )
        return not_run

    def _not_run_count(self) -> int:
        return len(self._not_run_checks())

    def _acceptance_result(self) -> tuple[str, str]:
        if self.options.cleanup_manifest_only and not self.ledger.failed:
            return "PASS", "PASS"
        if self.ledger.failed:
            code = (
                self._result_code
                if self._result_code != "PASS"
                else "ACCEPTANCE_CHECK_FAILED"
            )
            return "FAIL", code
        if self._executed_acceptance_checks == 0:
            return "INCONCLUSIVE", "NO_EXECUTED_ACCEPTANCE_CHECKS"
        return "PASS", "PASS"

    def _finalize(self) -> int:
        self.evidence.write_json("cleanup_manifest.json", self.cleanup.as_dict())
        self.evidence.ensure_required_files()
        summary = self.ledger.summary()
        summary["not_run"] = self._not_run_count()
        acceptance_status, result_code = self._acceptance_result()
        completed_at = datetime.now(timezone.utc)
        run_payload = {
            "run_id": self.run_id,
            "framework_status": self.framework_status,
            "acceptance_status": acceptance_status,
            "result_code": result_code,
            "executed_acceptance_checks": self._executed_acceptance_checks,
            "started_at": self.started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "elapsed_seconds": round(time.perf_counter() - self._started_clock, 3),
            "public_safe": self.public_safe,
            "application_label": self.config.application_label,
            "summary": summary,
            "not_run_checks": self._not_run_checks(),
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

    def _record_framework_exception(
        self,
        *,
        label: str,
        name: str,
        exc: BaseException,
    ) -> None:
        self.framework_status = "ERROR"
        try:
            error_path = self.evidence.write_error(label, exc)
        except Exception:
            error_path = None
        self._record(
            suite="FRAMEWORK",
            name=name,
            status=CheckStatus.FAIL,
            expected="completed",
            observed=type(exc).__name__,
            evidence_path=error_path,
        )

    def _close_adapter(self, label: str, adapter: Any) -> None:
        if adapter is None:
            return
        close = getattr(adapter, "close", None)
        if close is None:
            return
        try:
            close()
        except Exception as exc:
            self._record_framework_exception(
                label=f"{label}_close",
                name=f"{label.title()} adapter closed",
                exc=exc,
            )

    def _finalization_failed(self, exc: BaseException) -> int:
        self.framework_status = "ERROR"
        try:
            self.evidence.write_error("finalization", exc)
        except Exception:
            pass
        summary = self.ledger.summary()
        summary["not_run"] = self._not_run_count()
        try:
            self.evidence.write_json(
                "run.json",
                {
                    "run_id": self.run_id,
                    "framework_status": "ERROR",
                    "acceptance_status": "FAIL",
                    "result_code": "FINALIZATION_ERROR",
                    "executed_acceptance_checks": self._executed_acceptance_checks,
                    "summary": summary,
                    "not_run_checks": self._not_run_checks(),
                    "checks": [check.as_dict() for check in self.ledger.checks],
                    "cleanup_manifest": "cleanup_manifest.json",
                },
            )
        except Exception:
            pass
        try:
            self.console.final(
                framework_status="ERROR",
                acceptance_status="FAIL",
                summary=summary,
                evidence_path=self.evidence.display_path,
            )
        except Exception:
            pass
        return 1

    def run(self) -> int:
        self.console.start(self.run_id, self.public_safe)
        try:
            self.evidence.write_json("environment.json", self._environment())
            self.tracer.emit(
                "campaign.execution",
                phase="started",
                public_safe=self.public_safe,
            )
            if self.options.cleanup_manifest_only:
                self._run_manifest_only()
            else:
                self._run_campaign()
        except Exception as exc:
            self._record_framework_exception(
                label="framework",
                name="Framework execution completed",
                exc=exc,
            )
        finally:
            self._close_adapter("runtime", self.runtime)
            self._close_adapter("database", self.database)
            try:
                self.tracer.emit(
                    "campaign.execution",
                    phase="completed",
                    framework_status=self.framework_status,
                    acceptance_failed=self.ledger.failed,
                    elapsed_ms=round(
                        (time.perf_counter() - self._started_clock) * 1000, 3
                    ),
                )
            except Exception as exc:
                self._record_framework_exception(
                    label="trace_finalization",
                    name="Campaign trace finalized",
                    exc=exc,
                )
        try:
            return self._finalize()
        except Exception as exc:
            return self._finalization_failed(exc)