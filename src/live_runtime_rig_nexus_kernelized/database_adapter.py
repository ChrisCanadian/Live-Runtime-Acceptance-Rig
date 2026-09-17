"""Two-store safety adapter for kernelized Nexus acceptance.

The assembled TEST runtime reads protected legacy state while V5 owns canonical
connected state. The rig therefore backs up both SQLite stores into one exact
compound artifact before runtime start and validates both members on readback.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping

from live_runtime_rig.config import RigConfig
from live_runtime_rig.contracts import BackupProof, CleanupEntry


_V5_COUNT_TABLES = (
    "receipts",
    "turns",
    "tool_executions",
    "mode_activations",
    "memory_sources",
    "events",
    "character_sheets",
    "mode_definitions",
    "canonical_principal_mappings",
)
_LEGACY_COUNT_TABLES = (
    "InteractionLog",
    "ChatSessions",
    "DiscordLink",
    "Reflections",
)
_V5_PROTECTED_TABLES = (
    "character_sheets",
    "gauge_sets",
    "mode_definitions",
    "canonical_principal_mappings",
    "identity_relationship_overlays",
)
_LEGACY_PROTECTED_TABLES = (
    "Users",
    "UserProfile",
    "UserPreferences",
    "DiscordLink",
    "Reflections",
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
            table: int(connection.execute(
                f"SELECT COUNT(*) FROM {_quoted(table)}"
            ).fetchone()[0])
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
            digest.update(json.dumps(columns, separators=(",", ":")).encode("utf-8"))
            try:
                rows = connection.execute(
                    f"SELECT * FROM {_quoted(table)} ORDER BY rowid"
                ).fetchall()
            except sqlite3.OperationalError:
                rows = connection.execute(f"SELECT * FROM {_quoted(table)}").fetchall()
            for row in rows:
                for value in tuple(row):
                    if isinstance(value, bytes):
                        encoded = {"bytes_sha256": hashlib.sha256(value).hexdigest()}
                    else:
                        encoded = value
                    digest.update(
                        json.dumps(encoded, sort_keys=True, default=str).encode("utf-8")
                    )
                    digest.update(b"\0")
        return {
            "tables": tuple(included),
            "sha256": digest.hexdigest(),
        }
    finally:
        connection.close()


class KernelizedNexusDatabaseAdapter:
    def __init__(self, config: RigConfig) -> None:
        self.v5_database_path = Path(config.database_path).resolve()
        self.legacy_database_path = Path(os.environ["NEXUS_RIG_LEGACY_DB_PATH"]).resolve()

    def close(self) -> None:
        """All connections are method-scoped."""

    def verify_connection(self) -> Mapping[str, Any]:
        results: dict[str, bool] = {}
        for label, path in (
            ("v5", self.v5_database_path),
            ("legacy", self.legacy_database_path),
        ):
            if not path.is_file():
                results[label] = False
                continue
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                results[label] = connection.execute("SELECT 1").fetchone()[0] == 1
            finally:
                connection.close()
        return {"connected": all(results.values()), "stores": results}

    def backup(self, destination: Path) -> BackupProof:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="nexus-kernelized-backup-") as temp_dir:
            root = Path(temp_dir)
            v5_backup = root / "v5.sqlite"
            legacy_backup = root / "legacy.sqlite"
            _online_backup(self.v5_database_path, v5_backup)
            _online_backup(self.legacy_database_path, legacy_backup)
            if _integrity(v5_backup) != "ok" or _integrity(legacy_backup) != "ok":
                raise RuntimeError("compound Nexus backup member failed integrity check")
            manifest = {
                "schema_version": "1.0",
                "stores": {
                    "v5": {
                        "size_bytes": v5_backup.stat().st_size,
                        "sha256": _sha256(v5_backup),
                    },
                    "legacy": {
                        "size_bytes": legacy_backup.stat().st_size,
                        "sha256": _sha256(legacy_backup),
                    },
                },
            }
            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(v5_backup, arcname="v5.sqlite")
                archive.write(legacy_backup, arcname="legacy.sqlite")
                archive.writestr(
                    "manifest.json",
                    json.dumps(manifest, sort_keys=True, separators=(",", ":")),
                )
        return BackupProof(
            evidence_type="file",
            target=str(destination.resolve()),
            verified=True,
            integrity="ok",
            size_bytes=destination.stat().st_size,
            sha256=_sha256(destination),
            method="compound SQLite online backup: accepted V5 state + TEST legacy state",
        )

    def integrity_check(self, path: Path | None = None) -> Mapping[str, Any]:
        if path is None:
            v5 = _integrity(self.v5_database_path)
            legacy = _integrity(self.legacy_database_path)
            return {
                "result": "ok" if v5 == "ok" and legacy == "ok" else "failed",
                "stores": {"v5": v5, "legacy": legacy},
            }
        candidate = Path(path).resolve()
        if not zipfile.is_zipfile(candidate):
            return {"result": "failed", "reason": "compound_backup_expected"}
        with tempfile.TemporaryDirectory(prefix="nexus-kernelized-verify-") as temp_dir:
            with zipfile.ZipFile(candidate, "r") as archive:
                names = set(archive.namelist())
                required = {"v5.sqlite", "legacy.sqlite", "manifest.json"}
                if not required.issubset(names):
                    return {"result": "failed", "reason": "backup_members_missing"}
                archive.extract("v5.sqlite", temp_dir)
                archive.extract("legacy.sqlite", temp_dir)
                manifest = json.loads(archive.read("manifest.json"))
            v5 = Path(temp_dir) / "v5.sqlite"
            legacy = Path(temp_dir) / "legacy.sqlite"
            member_checks = {
                "v5": _integrity(v5),
                "legacy": _integrity(legacy),
            }
            digest_checks = {
                "v5": _sha256(v5) == manifest["stores"]["v5"]["sha256"],
                "legacy": _sha256(legacy) == manifest["stores"]["legacy"]["sha256"],
            }
            ok = all(value == "ok" for value in member_checks.values()) and all(
                digest_checks.values()
            )
            return {
                "result": "ok" if ok else "failed",
                "stores": member_checks,
                "member_digests_verified": digest_checks,
            }

    def snapshot_state(self) -> Mapping[str, Any]:
        return {
            "v5": {
                "integrity": _integrity(self.v5_database_path),
                "counts": _counts(self.v5_database_path, _V5_COUNT_TABLES),
            },
            "legacy": {
                "integrity": _integrity(self.legacy_database_path),
                "counts": _counts(self.legacy_database_path, _LEGACY_COUNT_TABLES),
            },
        }

    def protected_state_snapshot(self) -> Mapping[str, Any]:
        return {
            "v5": _fingerprint(self.v5_database_path, _V5_PROTECTED_TABLES),
            "legacy": _fingerprint(self.legacy_database_path, _LEGACY_PROTECTED_TABLES),
        }

    def verify_created_record(
        self, resource_type: str, identifier: str
    ) -> Mapping[str, Any] | None:
        if resource_type == "v5_receipt":
            table = "receipts"
            key = "receipt_id"
            path = self.v5_database_path
        else:
            raise ValueError(f"unsupported Nexus acceptance resource type: {resource_type}")
        if table not in _present_tables(path):
            return None
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
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
                "Review only. If cleanup is authorized later, require this exact identifier "
                "plus the acceptance run marker; never delete by user or time range."
            ),
        )


def create_database_adapter(config: RigConfig) -> KernelizedNexusDatabaseAdapter:
    return KernelizedNexusDatabaseAdapter(config)
