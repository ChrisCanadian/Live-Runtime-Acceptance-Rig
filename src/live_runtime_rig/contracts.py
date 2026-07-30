"""Stable, application-neutral contracts used by adapters and cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .assertions import CheckStatus


@dataclass(frozen=True)
class CheckSpec:
    """An explicit acceptance observation returned by a case."""

    name: str
    status: CheckStatus
    expected: Any
    observed: Any
    evidence_path: str | None = None
    heuristic: bool = False


@dataclass(frozen=True)
class CleanupEntry:
    """A precisely scoped resource created by the current run."""

    resource_type: str
    identifier: str
    table_or_path: str
    run_marker: str
    notes: str = ""
    cleanup_key: str = ""
    cleanup_instruction: str = ""


@dataclass
class CaseContext:
    """State shared with cases without exposing runner internals."""

    run_id: str
    marker: str
    public_safe: bool
    settings: Mapping[str, Any]
    evidence: Any
    tracer: Any
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseResult:
    """Explicit result returned by every acceptance case."""

    checks: list[CheckSpec]
    evidence: Mapping[str, Any] = field(default_factory=dict)
    cleanup_entries: list[CleanupEntry] = field(default_factory=list)
    state_updates: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class RuntimeAdapter(Protocol):
    """Connect the framework to the application's real public boundary."""

    def start(self) -> None: ...

    def close(self) -> None: ...

    def health(self) -> Mapping[str, Any]: ...

    def request(self, method: str, path: str, **kwargs: Any) -> Any: ...

    def direct_readiness_probe(self) -> Mapping[str, Any]: ...

    def list_capabilities(self) -> Sequence[str]: ...


@runtime_checkable
class DatabaseAdapter(Protocol):
    """Connect the framework to durable application state."""

    def verify_connection(self) -> Mapping[str, Any]: ...

    def backup(self, destination: Path) -> Mapping[str, Any]: ...

    def integrity_check(self, path: Path | None = None) -> Mapping[str, Any]: ...

    def snapshot_state(self) -> Mapping[str, Any]: ...

    def verify_created_record(
        self, resource_type: str, identifier: str
    ) -> Mapping[str, Any] | None: ...

    def protected_state_snapshot(self) -> Mapping[str, Any]: ...

    def cleanup_manifest_entry(
        self,
        resource_type: str,
        identifier: str,
        marker: str,
        *,
        notes: str = "",
    ) -> CleanupEntry: ...


class AcceptanceCase(Protocol):
    """A runnable case with an explicit suite and name."""

    name: str
    suite: str

    def run(
        self,
        runtime: RuntimeAdapter,
        database: DatabaseAdapter,
        context: CaseContext,
    ) -> CaseResult: ...
