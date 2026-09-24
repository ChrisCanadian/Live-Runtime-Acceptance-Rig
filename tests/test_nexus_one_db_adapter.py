from __future__ import annotations

import sqlite3
from pathlib import Path

from live_runtime_rig.config import RigConfig
from live_runtime_rig_nexus_kernelized.database_adapter import (
    KernelizedNexusDatabaseAdapter,
)


def _config(root: Path, database: Path) -> RigConfig:
    env = root / "acceptance.env"
    env.write_text(
        "\n".join(
            (
                "RIG_RUNTIME_ADAPTER=unused:runtime",
                "RIG_DATABASE_ADAPTER=unused:database",
                "RIG_CASES=unused:cases",
                f"RIG_DATABASE_PATH={database}",
                f"RIG_EVIDENCE_DIR={root / 'evidence'}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return RigConfig.load(env)


def _database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE receipts(receipt_id TEXT PRIMARY KEY);
            CREATE TABLE canonical_principal_mappings(
                mapping_id TEXT PRIMARY KEY,
                owner_key TEXT NOT NULL
            );
            CREATE TABLE owner_profiles(
                owner_key TEXT PRIMARY KEY,
                display_name TEXT
            );
            INSERT INTO canonical_principal_mappings VALUES ('m1','owner:nexus-user-18');
            INSERT INTO owner_profiles VALUES ('owner:nexus-user-18','Chris');
            """
        )


def test_kernelized_database_adapter_uses_one_physical_authority(tmp_path: Path) -> None:
    database = tmp_path / "canonical.sqlite"
    _database(database)
    adapter = KernelizedNexusDatabaseAdapter(_config(tmp_path, database))

    assert adapter.verify_connection() == {
        "connected": True,
        "authority": "canonical",
        "persistence_authority_count": 1,
    }
    assert adapter.integrity_check()["result"] == "ok"
    assert adapter.snapshot_state()["persistence_authority_count"] == 1

    protected = adapter.protected_state_snapshot()
    assert protected["persistence_authority_count"] == 1
    assert protected["canonical"]["tables"] == (
        "canonical_principal_mappings",
        "owner_profiles",
    )


def test_kernelized_database_backup_is_single_sqlite_not_compound_archive(
    tmp_path: Path,
) -> None:
    database = tmp_path / "canonical.sqlite"
    _database(database)
    adapter = KernelizedNexusDatabaseAdapter(_config(tmp_path, database))
    backup = tmp_path / "backup.sqlite"

    proof = adapter.backup(backup)

    assert proof.method == "single canonical SQLite online backup"
    assert adapter.integrity_check(backup)["result"] == "ok"
    with sqlite3.connect(backup) as connection:
        assert connection.execute(
            "SELECT owner_key FROM canonical_principal_mappings"
        ).fetchone() == ("owner:nexus-user-18",)
