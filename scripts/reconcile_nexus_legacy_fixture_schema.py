from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


_SAFE_TYPE = re.compile(r"^[A-Za-z0-9_(), ]*$")
_MIGRATION_OWNED = {
    "CognitiveNodes",
    "GlobalTraits_Constants",
    "GlobalTraits_Gauges",
    "UserTraitWeights",
}


def _quote(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("invalid SQLite identifier in production schema snapshot")
    return '"' + value.replace('"', '""') + '"'


def _declared_type(value: Any) -> str:
    text = str(value or "").strip()
    if not _SAFE_TYPE.fullmatch(text):
        raise ValueError(f"unsafe SQLite type in production schema snapshot: {text!r}")
    return text


def _existing_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _create_table(
    connection: sqlite3.Connection,
    table: str,
    columns: list[dict[str, Any]],
) -> None:
    if not columns:
        raise ValueError(f"production schema snapshot has no columns for {table}")

    pk = sorted(
        (
            (int(column.get("pk") or 0), str(column["name"]))
            for column in columns
            if int(column.get("pk") or 0) > 0
        ),
        key=lambda item: item[0],
    )
    single_pk = pk[0][1] if len(pk) == 1 else None

    definitions: list[str] = []
    for column in columns:
        name = str(column["name"])
        pieces = [_quote(name)]
        declared = _declared_type(column.get("type"))
        if declared:
            pieces.append(declared)
        if name == single_pk:
            pieces.append("PRIMARY KEY")
        elif bool(column.get("notnull")):
            pieces.append("NOT NULL")
        definitions.append(" ".join(pieces))

    if len(pk) > 1:
        definitions.append(
            "PRIMARY KEY (" + ", ".join(_quote(name) for _order, name in pk) + ")"
        )

    connection.execute(
        f"CREATE TABLE {_quote(table)} ({', '.join(definitions)})"
    )


def _reconstruct_missing_schema(
    legacy_db: Path,
    schema_manifest: Path,
) -> dict[str, Any]:
    try:
        manifest = json.loads(schema_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read production schema snapshot: {schema_manifest}") from exc
    if not isinstance(manifest, dict) or not manifest:
        raise SystemExit("production schema snapshot is empty or invalid")

    connection = sqlite3.connect(legacy_db)
    created: list[str] = []
    try:
        existing = _existing_tables(connection)
        for table in sorted(manifest):
            if table in existing or table in _MIGRATION_OWNED:
                continue
            columns = manifest[table]
            if not isinstance(columns, list):
                raise SystemExit(f"invalid production schema entry for {table}")
            _create_table(connection, str(table), columns)
            created.append(str(table))
        connection.commit()
    finally:
        connection.close()

    return {
        "schema_manifest": str(schema_manifest),
        "manifest_table_count": len(manifest),
        "migration_owned_exclusions": tuple(sorted(_MIGRATION_OWNED)),
        "created_empty_table_count": len(created),
        "created_empty_tables": tuple(created),
        "existing_tables_unchanged": True,
        "production_rows_invented": False,
    }


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load production migration: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply_trait_migration(
    legacy_db: Path,
    production_root: Path,
    user_ids: tuple[int, ...],
) -> dict[str, Any]:
    migration = production_root / "migrations" / "migrate_traits_v2.py"
    if not migration.is_file():
        raise SystemExit(f"pinned production trait migration missing: {migration}")

    module = _load_module(migration, "nexus_rig_migrate_traits_v2")
    ensure_schema = getattr(module, "ensure_schema", None)
    seed_gauges = getattr(module, "seed_gauges", None)
    ensure_user_row = getattr(module, "ensure_user_row", None)
    if not all(callable(fn) for fn in (ensure_schema, seed_gauges, ensure_user_row)):
        raise SystemExit(f"pinned production trait migration contract changed: {migration}")

    connection = sqlite3.connect(legacy_db)
    try:
        ensure_schema(connection)
        seed_gauges(connection)
        for user_id in user_ids:
            ensure_user_row(connection, user_id)
        counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in (
                "GlobalTraits_Constants",
                "GlobalTraits_Gauges",
                "UserTraitWeights",
            )
        }
    finally:
        connection.close()

    return {
        "migration": str(migration),
        "schema_from_pinned_production_migration": True,
        "gauges_seeded_from_pinned_production_migration": True,
        "fixture_user_ids_ensured": user_ids,
        "row_counts": counts,
    }


def _integrity(path: Path) -> str:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing"
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-db", type=Path, required=True)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--production-schema-manifest", type=Path, required=True)
    parser.add_argument("--user-id", type=int, action="append", dest="user_ids")
    args = parser.parse_args()

    legacy_db = args.legacy_db.resolve()
    production_root = args.production_root.resolve()
    schema_manifest = args.production_schema_manifest.resolve()
    user_ids = tuple(args.user_ids or (18, 19))

    if not legacy_db.is_file():
        raise SystemExit(f"disposable legacy database missing: {legacy_db}")
    if not production_root.is_dir():
        raise SystemExit(f"pinned production checkout missing: {production_root}")
    if not schema_manifest.is_file():
        raise SystemExit(f"production schema snapshot missing: {schema_manifest}")

    schema = _reconstruct_missing_schema(legacy_db, schema_manifest)
    traits = _apply_trait_migration(legacy_db, production_root, user_ids)
    integrity = _integrity(legacy_db)
    if integrity != "ok":
        raise SystemExit(f"legacy fixture integrity failed after reconciliation: {integrity}")

    print(
        json.dumps(
            {
                "status": "RECONCILED",
                "classification": "DEVELOPMENT_FIXTURE",
                "source_state_mutated": False,
                "legacy_integrity": integrity,
                "production_schema_compatibility": schema,
                "traits_v2": traits,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
