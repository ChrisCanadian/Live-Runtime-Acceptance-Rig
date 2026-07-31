"""SQLite adapter with verified backup and strict table allowlisting."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from live_runtime_rig.config import RigConfig
from live_runtime_rig.contracts import BackupProof, CleanupEntry
from live_runtime_rig.sqlite_safety import (
    count_rows,
    integrity_check,
    read_only_connection,
    verified_sqlite_backup,
)

ALLOWED_TABLES = frozenset(
    {
        "users",
        "work_orders",
        "work_order_events",
        "audit_receipts",
    }
)


class WorkOrderDatabaseAdapter:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path


    def close(self) -> None:
        """This adapter opens only method-scoped connections."""

    def verify_connection(self) -> Mapping[str, Any]:
        with read_only_connection(self.database_path) as connection:
            value = connection.execute("SELECT 1").fetchone()[0]
        return {"connected": value == 1}

    def backup(self, destination: Path) -> BackupProof:
        return verified_sqlite_backup(self.database_path, destination)

    def integrity_check(self, path: Path | None = None) -> Mapping[str, Any]:
        target = self.database_path if path is None else path
        return {"result": integrity_check(target)}

    def snapshot_state(self) -> Mapping[str, Any]:
        with read_only_connection(self.database_path) as connection:
            counts = {
                table: count_rows(
                    connection,
                    table,
                    allowed_tables=ALLOWED_TABLES,
                )
                for table in sorted(ALLOWED_TABLES)
            }
        return {"table_counts": counts, "integrity": "ok"}

    def verify_created_record(
        self, resource_type: str, identifier: str
    ) -> Mapping[str, Any] | None:
        queries = {
            "work_order": "SELECT * FROM work_orders WHERE id = ?",
            "event": "SELECT * FROM work_order_events WHERE id = ?",
            "audit_receipt": "SELECT * FROM audit_receipts WHERE id = ?",
        }
        if resource_type not in queries:
            raise ValueError(f"Unsupported resource type: {resource_type!r}")
        with read_only_connection(self.database_path) as connection:
            row = connection.execute(
                queries[resource_type], (identifier,)
            ).fetchone()
        return dict(row) if row is not None else None

    def protected_state_snapshot(self) -> Mapping[str, Any]:
        with read_only_connection(self.database_path) as connection:
            rows = [
                dict(row)
                for row in connection.execute(
                    "SELECT id, display_name, role FROM users ORDER BY id"
                ).fetchall()
            ]
        encoded = json.dumps(
            rows, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return {
            "users_count": len(rows),
            "users_sha256": hashlib.sha256(encoded).hexdigest(),
        }

    def resources_for_work_order(
        self, work_order_id: str, marker: str
    ) -> Mapping[str, list[Mapping[str, Any]]]:
        with read_only_connection(self.database_path) as connection:
            events = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT id, work_order_id, marker, event_type
                    FROM work_order_events
                    WHERE work_order_id = ? AND marker = ?
                    ORDER BY created_at, id
                    """,
                    (work_order_id, marker),
                ).fetchall()
            ]
            receipts = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT id, work_order_id, marker, action
                    FROM audit_receipts
                    WHERE work_order_id = ? AND marker = ?
                    ORDER BY created_at, id
                    """,
                    (work_order_id, marker),
                ).fetchall()
            ]
        return {"events": events, "audit_receipts": receipts}

    def cleanup_manifest_entry(
        self,
        resource_type: str,
        identifier: str,
        marker: str,
        *,
        notes: str = "",
    ) -> CleanupEntry:
        table_by_type = {
            "work_order": "work_orders",
            "event": "work_order_events",
            "audit_receipt": "audit_receipts",
        }
        if resource_type not in table_by_type:
            raise ValueError(f"Unsupported cleanup resource: {resource_type!r}")
        return CleanupEntry(
            resource_type=resource_type,
            identifier=identifier,
            table_or_path=table_by_type[resource_type],
            run_marker=marker,
            notes=notes,
            cleanup_key=f"work_order_example.remove_exact_{resource_type}",
            cleanup_instruction=(
                "Use the adapter callback with both this identifier and the exact "
                "run marker; do not perform an unscoped delete."
            ),
        )


def create_database_adapter(config: RigConfig) -> WorkOrderDatabaseAdapter:
    return WorkOrderDatabaseAdapter(config.database_path)
