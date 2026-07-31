from __future__ import annotations

import sqlite3

import pytest

from live_runtime_rig.sqlite_safety import (
    BackupVerificationError,
    allowlisted_identifier,
    count_rows,
    integrity_check,
    read_only_connection,
    verified_sqlite_backup,
)


def _create_database(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO records (value) VALUES (?)", ("example",))
        connection.commit()


def test_verified_backup_uses_native_api_and_passes_integrity(tmp_path) -> None:
    source = tmp_path / "source.sqlite"
    destination = tmp_path / "backups" / "copy.sqlite"
    _create_database(source)

    result = verified_sqlite_backup(source, destination)

    assert result.verified is True
    assert result.integrity == "ok"
    assert result.method == "sqlite3.Connection.backup"
    assert len(result.sha256) == 64
    with read_only_connection(destination) as connection:
        assert connection.execute("SELECT value FROM records").fetchone()[0] == "example"


def test_invalid_database_fails_integrity_verification(tmp_path) -> None:
    invalid = tmp_path / "invalid.sqlite"
    invalid.write_bytes(b"not a sqlite database")
    with pytest.raises(BackupVerificationError):
        integrity_check(invalid)


def test_missing_source_does_not_create_empty_backup(tmp_path) -> None:
    destination = tmp_path / "copy.sqlite"
    with pytest.raises(BackupVerificationError):
        verified_sqlite_backup(tmp_path / "missing.sqlite", destination)
    assert destination.exists() is False


def test_table_identifier_requires_strict_allowlist(tmp_path) -> None:
    database = tmp_path / "source.sqlite"
    _create_database(database)
    assert allowlisted_identifier("records", {"records"}) == '"records"'
    with pytest.raises(ValueError, match="not allowlisted"):
        allowlisted_identifier("records; DROP TABLE records", {"records"})
    with read_only_connection(database) as connection:
        assert count_rows(
            connection, "records", allowed_tables={"records"}
        ) == 1
