"""Small SQLite safety primitives for adapters and tests."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import quote

from .contracts import BackupProof


class BackupVerificationError(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_only_connection(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    uri = f"file:{quote(resolved.as_posix(), safe='/:')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def integrity_check(path: Path) -> str:
    if not path.is_file() or path.stat().st_size == 0:
        raise BackupVerificationError("SQLite file is missing or empty")
    try:
        with read_only_connection(path) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.DatabaseError as exc:
        raise BackupVerificationError("SQLite integrity check could not run") from exc
    if result != "ok":
        raise BackupVerificationError(f"SQLite integrity check failed: {result}")
    return result


def verified_sqlite_backup(source: Path, destination: Path) -> BackupProof:
    if not source.is_file() or source.stat().st_size == 0:
        raise BackupVerificationError("Source SQLite database is missing or empty")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite backup: {destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(str(source), timeout=30)
    destination_connection = sqlite3.connect(str(destination), timeout=30)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()
    verified = integrity_check(destination)
    return BackupProof(
        evidence_type="file",
        target=str(destination.resolve()),
        verified=verified == "ok",
        integrity=verified,
        size_bytes=destination.stat().st_size,
        sha256=file_sha256(destination),
        method="sqlite3.Connection.backup",
    )


def allowlisted_identifier(identifier: str, allowed: Iterable[str]) -> str:
    allowed_set = frozenset(allowed)
    if identifier not in allowed_set:
        raise ValueError(f"Table is not allowlisted: {identifier!r}")
    return f'"{identifier}"'


def count_rows(
    connection: sqlite3.Connection,
    table: str,
    *,
    allowed_tables: Iterable[str],
) -> int:
    quoted = allowlisted_identifier(table, allowed_tables)
    return int(connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])