"""Single-authority SQLite adapter for kernelized Nexus acceptance.

The converged NDKA target has one physical canonical SQLite authority. Production
donor behavior may still consume compatibility projections, but the acceptance
rig must not manufacture a second persistence authority in order to exercise it.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from live_runtime_rig.config import RigConfig
from live_runtime_rig.contracts import BackupProof, CleanupEntry


_COUNT_TABLES = (
    "receipts",
    "sessions",
    "turns",
    "tool_executions",
    "mode_activations",
    "memory_sources",
    "events",
    "surface_events",
    "character_sheets",
    "mode_definitions",
    "canonical_principal_mappings",
    "owner_profiles",
    "reflections",
    "historical_reflection_archive",
    "imported_v2_summaries",
    "legacy_authoritative_records",
)

_PROTECTED_TABLES = (
    "canonical_principal_mappings",
    "character_sheets",
    "character_sheet_versions",
    "character_traits",
    "gauge_set_versions",
    "gauges",
    "identity_contracts",
    "identity_voice_profiles",
    "identity_relationship_overlays",
    "identity_visual_profiles",
    "identity_character_canons",
    "identity_source_lineage",
    "owner_profiles",
    "mode_definitions",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity(path: Path) -> str:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing"
    finally:
        connection.close()


def _online_backup(source: Path, target: Path) -> None:
    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    target_connection = sqlite3.connect(target)
    try:
        source_connection.execute("PRAGMA query_only=ON")
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()


def _present_tables(path: Path) -> frozenset[str]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return frozenset(str(row[0]) for row in rows)
    finally:
        connection.close()


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _counts(path: Path, candidates: tuple[str, ...]) -> Mapping[str, int]:
    present = _present_tables(path)
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {
            table: int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {_quoted(table)}"
                ).fetchone()[0]
            )
            for table in candidates
            if table in present
        }
    finally:
        connection.close()


def _fingerprint(path: Path, candidates: tuple[str, ...]) -> Mapping[str, Any]:
    present = _present_tables(path)
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    digest = hashlib.sha256()
    included: list[str] = []
    try:
        for table in sorted(set(candidates) & set(present)):
            included.append(table)
            digest.update(table.encode("utf-8"))
            columns = [
                str(row[1])
                for row in connection.execute(
                    f"PRAGMA table_info({_quoted(table)})"
                ).fetchall()
            ]
            digest.update(
                repr(tuple(columns)).encode("utf-8")
            )
            try:
                rows = connection.execute(
                    f"SELECT * FROM {_quoted(table)} ORDER BY rowid"
                ).fetchall()
            except sqlite3.OperationalError:
                rows = connection.execute(
                    f"SELECT * FROM {_quoted(table)}"
                ).fetchall()
            for row in rows:
                for value in tuple(row):
                    if isinstance(value, bytes):
                        encoded = hashlib.sha256(value).hexdigest()
                    else:
                        encoded = repr(value)
                    digest.update(str(encoded).encode("utf-8"))
                    digest.update(b"\0")
        return {"tables": tuple(included), "sha256": digest.hexdigest()}
    finally:
        connection.close()


class KernelizedNexusDatabaseAdapter:
    def __init__(self, config: RigConfig) -> None:
        self.database_path = Path(config.database_path).resolve()

    def close(self) -> None:
        """All connections are method-scoped."""

    def verify_connection(self) -> Mapping[str, Any]:
        if not self.database_path.is_file():
            return {
                "connected": False,
                "authority": "canonical",
                "persistence_authority_count": 0,
            }
        connection = sqlite3.connect(
            f"file:{self.database_path}?mode=ro", uri=True
        )
        try:
            connected = connection.execute("SELECT 1").fetchone()[0] == 1
        finally:
            connection.close()
        return {
            "connected": connected,
            "authority": "canonical",
            "persistence_authority_count": 1 if connected else 0,
        }

    def backup(self, destination: Path) -> BackupProof:
        destination.parent.mkdir(parents=True, exist_ok=True)
        _online_backup(self.database_path, destination)
        integrity = _integrity(destination)
        if integrity != "ok":
            raise RuntimeError("canonical Nexus backup failed integrity check")
        return BackupProof(
            evidence_type="file",
            target=str(destination.resolve()),
            verified=True,
            integrity=integrity,
            size_bytes=destination.stat().st_size,
            sha256=_sha256(destination),
            method="single canonical SQLite online backup",
        )

    def integrity_check(self, path: Path | None = None) -> Mapping[str, Any]:
        candidate = self.database_path if path is None else Path(path).resolve()
        if not candidate.is_file():
            return {"result": "failed", "reason": "database_missing"}
        result = _integrity(candidate)
        return {
            "result": result,
            "authority": "canonical",
            "persistence_authority_count": 1,
        }

    def snapshot_state(self) -> Mapping[str, Any]:
        return {
            "canonical": {
                "integrity": _integrity(self.database_path),
                "counts": _counts(self.database_path, _COUNT_TABLES),
            },
            "persistence_authority_count": 1,
        }

    def protected_state_snapshot(self) -> Mapping[str, Any]:
        return {
            "canonical": _fingerprint(self.database_path, _PROTECTED_TABLES),
            "persistence_authority_count": 1,
        }

    def verify_created_record(
        self, resource_type: str, identifier: str
    ) -> Mapping[str, Any] | None:
        table_by_type = {
            "v5_receipt": ("receipts", "receipt_id"),
            "mode_activation": ("mode_activations", "activation_id"),
            "tool_execution": ("tool_executions", "execution_id"),
        }
        target = table_by_type.get(resource_type)
        if target is None:
            raise ValueError(
                f"unsupported Nexus acceptance resource type: {resource_type}"
            )
        table, key = target
        if table not in _present_tables(self.database_path):
            return None
        connection = sqlite3.connect(
            f"file:{self.database_path}?mode=ro", uri=True
        )
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                f"SELECT * FROM {_quoted(table)} WHERE {_quoted(key)} = ?",
                (identifier,),
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            connection.close()

    def cleanup_manifest_entry(
        self,
        resource_type: str,
        identifier: str,
        marker: str,
        *,
        notes: str = "",
    ) -> CleanupEntry:
        table_by_type = {
            "v5_receipt": "receipts",
            "mode_activation": "mode_activations",
            "tool_execution": "tool_executions",
        }
        table = table_by_type.get(resource_type)
        if table is None:
            raise ValueError(f"unsupported Nexus cleanup resource: {resource_type}")
        return CleanupEntry(
            resource_type=resource_type,
            identifier=identifier,
            table_or_path=table,
            run_marker=marker,
            notes=notes,
            cleanup_key=f"nexus_kernelized.review_exact_{resource_type}",
            cleanup_instruction=(
                "Review only. If cleanup is authorized later, require this exact "
                "identifier plus the acceptance run marker; never delete by user "
                "or time range."
            ),
        )


def create_database_adapter(config: RigConfig) -> KernelizedNexusDatabaseAdapter:
    return KernelizedNexusDatabaseAdapter(config)
