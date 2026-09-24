from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any


_SAFE_TYPE = re.compile(r"^[A-Za-z0-9_(), ]*$")
_SCHEMA_EXCLUSIONS = {
    "CognitiveNodes",
    "GlobalTraits_Constants",
    "GlobalTraits_Gauges",
    "UserTraitWeights",
}


def _integrity(path: Path) -> str:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
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


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _quote_identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("invalid SQLite identifier in production schema snapshot")
    return '"' + value.replace('"', '""') + '"'


def _declared_type(value: Any) -> str:
    text = str(value or "").strip()
    if not _SAFE_TYPE.fullmatch(text):
        raise ValueError(f"unsafe declared SQLite type in production schema snapshot: {text!r}")
    return text


def _create_table_from_snapshot_schema(
    connection: sqlite3.Connection,
    table: str,
    columns: list[dict[str, Any]],
) -> None:
    if not columns:
        raise ValueError(f"production schema snapshot has no columns for {table}")

    pk_columns = sorted(
        (
            (int(column.get("pk") or 0), str(column["name"]))
            for column in columns
            if int(column.get("pk") or 0) > 0
        ),
        key=lambda item: item[0],
    )
    single_pk = pk_columns[0][1] if len(pk_columns) == 1 else None

    definitions: list[str] = []
    for column in columns:
        name = str(column["name"])
        declared = _declared_type(column.get("type"))
        pieces = [_quote_identifier(name)]
        if declared:
            pieces.append(declared)
        if single_pk == name:
            pieces.append("PRIMARY KEY")
        elif bool(column.get("notnull")):
            pieces.append("NOT NULL")
        definitions.append(" ".join(pieces))

    if len(pk_columns) > 1:
        definitions.append(
            "PRIMARY KEY ("
            + ", ".join(_quote_identifier(name) for _order, name in pk_columns)
            + ")"
        )

    connection.execute(
        f"CREATE TABLE {_quote_identifier(table)} ({', '.join(definitions)})"
    )


def _ensure_snapshot_schema_compatibility(
    legacy: Path,
    schema_manifest: Path,
) -> dict[str, Any]:
    """Backfill missing schema only in the disposable legacy copy.

    The accepted V5 production snapshot supplies table/column shape, not row
    data. Existing source tables are never altered. Tables with authoritative
    production migrations/seeding are excluded and handled below.
    """

    if not schema_manifest.is_file():
        raise SystemExit(f"production schema snapshot missing: {schema_manifest}")
    try:
        manifest = json.loads(schema_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read production schema snapshot: {schema_manifest}") from exc
    if not isinstance(manifest, dict) or not manifest:
        raise SystemExit("production schema snapshot is empty or invalid")

    connection = sqlite3.connect(legacy)
    created: list[str] = []
    try:
        existing = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in sorted(manifest):
            if table in existing or table in _SCHEMA_EXCLUSIONS:
                continue
            columns = manifest[table]
            if not isinstance(columns, list):
                raise SystemExit(f"invalid production schema entry for table {table}")
            _create_table_from_snapshot_schema(connection, str(table), columns)
            created.append(str(table))
        connection.commit()
    finally:
        connection.close()

    return {
        "schema_manifest": str(schema_manifest),
        "manifest_table_count": len(manifest),
        "excluded_seeded_tables": tuple(sorted(_SCHEMA_EXCLUSIONS)),
        "created_empty_table_count": len(created),
        "created_empty_tables": tuple(created),
        "existing_tables_unchanged": True,
        "production_rows_invented": False,
    }


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load fixture migration: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_production_root(target_dir: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        root = explicit.resolve()
    else:
        try:
            cache_root = target_dir.parents[2]
        except IndexError as exc:
            raise SystemExit("cannot infer production checkout for fixture reconstruction") from exc
        root = cache_root / "repos" / "nexus-synapse-runtime"
    if not root.is_dir():
        raise SystemExit(f"production checkout not found for fixture reconstruction: {root}")
    return root


def _resolve_schema_manifest(target_dir: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        manifest = explicit.resolve()
    else:
        try:
            cache_root = target_dir.parents[2]
        except IndexError as exc:
            raise SystemExit("cannot infer V5 checkout for schema reconstruction") from exc
        manifest = (
            cache_root
            / "repos"
            / "nexus-v5-reconstruction"
            / "evidence"
            / "production_snapshot_schema.json"
        )
    if not manifest.is_file():
        raise SystemExit(f"production schema snapshot not found: {manifest}")
    return manifest


def _ensure_trait_fixture(
    legacy: Path,
    production_root: Path,
    *,
    user_ids: tuple[int, ...] = (18, 19),
) -> dict[str, Any]:
    """Use the pinned production trait migration against the disposable copy."""

    migration = production_root / "migrations" / "migrate_traits_v2.py"
    if not migration.is_file():
        raise SystemExit(f"pinned production trait migration missing: {migration}")
    module = _load_module(migration, "nexus_rig_production_migrate_traits_v2")
    ensure_schema = getattr(module, "ensure_schema", None)
    seed_gauges = getattr(module, "seed_gauges", None)
    ensure_user_row = getattr(module, "ensure_user_row", None)
    if not all(callable(item) for item in (ensure_schema, seed_gauges, ensure_user_row)):
        raise SystemExit(f"pinned production trait migration contract changed: {migration}")

    connection = sqlite3.connect(legacy)
    try:
        ensure_schema(connection)
        seed_gauges(connection)
        for user_id in user_ids:
            ensure_user_row(connection, int(user_id))
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


def _ensure_cognitive_nodes_fixture(
    legacy: Path,
    production_root: Path,
) -> dict[str, Any]:
    """Repair only the disposable copy when an older source DB lacks CognitiveNodes."""

    connection = sqlite3.connect(legacy)
    try:
        existed = _table_exists(connection, "CognitiveNodes")
        if not existed:
            connection.execute(
                """
                CREATE TABLE CognitiveNodes (
                    NodeID INTEGER PRIMARY KEY AUTOINCREMENT,
                    UserID INTEGER,
                    NodeName TEXT NOT NULL,
                    DisplayName TEXT NOT NULL,
                    Description TEXT NOT NULL,
                    TriggerIntents TEXT DEFAULT '{}',
                    TriggerTopics TEXT DEFAULT '{}',
                    TriggerEmotions TEXT DEFAULT '{}',
                    TriggerMoods TEXT DEFAULT '{}',
                    IsAlarmNode INTEGER DEFAULT 0,
                    ActivationThreshold REAL DEFAULT 0.3,
                    IsActive INTEGER DEFAULT 1,
                    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    BehavioralInstruction TEXT DEFAULT ''
                )
                """
            )
            connection.commit()

        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(CognitiveNodes)").fetchall()
        }
        if "BehavioralInstruction" not in columns:
            connection.execute(
                "ALTER TABLE CognitiveNodes ADD COLUMN BehavioralInstruction TEXT DEFAULT ''"
            )
            connection.commit()

        global_before = int(
            connection.execute(
                "SELECT COUNT(*) FROM CognitiveNodes WHERE UserID IS NULL"
            ).fetchone()[0]
        )
    finally:
        connection.close()

    migration = production_root / "migrations" / "migrate_010_global_cognitive_nodes.py"
    seeded_from_donor = False
    if global_before == 0:
        if not migration.is_file():
            raise SystemExit(f"pinned production CognitiveNodes migration missing: {migration}")
        module = _load_module(migration, "nexus_rig_production_migrate_010")
        run = getattr(module, "run", None)
        if not callable(run):
            raise SystemExit(f"pinned production CognitiveNodes migration has no run(): {migration}")
        run(str(legacy))
        seeded_from_donor = True

    verify = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
    try:
        verify.execute("PRAGMA query_only=ON")
        total = int(verify.execute("SELECT COUNT(*) FROM CognitiveNodes").fetchone()[0])
        global_count = int(
            verify.execute(
                "SELECT COUNT(*) FROM CognitiveNodes WHERE UserID IS NULL"
            ).fetchone()[0]
        )
        columns = tuple(
            str(row[1])
            for row in verify.execute("PRAGMA table_info(CognitiveNodes)").fetchall()
        )
    finally:
        verify.close()

    if global_count <= 0:
        raise SystemExit("disposable CognitiveNodes reconstruction produced no global nodes")

    return {
        "source_table_present": existed,
        "fixture_table_created": not existed,
        "seeded_from_pinned_production_migration": seeded_from_donor,
        "migration": str(migration),
        "total_rows": total,
        "global_rows": global_count,
        "columns": columns,
    }


def _linked_identities(legacy: Path) -> list[tuple[str, str]]:
    connection = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute(
            "SELECT DiscordID, UserID FROM DiscordLink ORDER BY UserID, DiscordID"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()

    result: list[tuple[str, str]] = []
    seen_discord: set[str] = set()
    for discord_id, user_id in rows:
        discord = str(discord_id).strip()
        user = str(user_id).strip()
        if not discord or not user or discord in seen_discord:
            continue
        seen_discord.add(discord)
        result.append((discord, user))
    return result


def _write_identity_env(path: Path, identities: list[tuple[str, str]]) -> None:
    selected = identities[:2]
    owners = {user_id: "nexus" for _discord_id, user_id in selected}
    lines: list[str] = []
    if selected:
        lines.append(f"NEXUS_RIG_PRIMARY_DISCORD_ID={selected[0][0]}")
    if len(selected) > 1:
        lines.append(f"NEXUS_RIG_SECONDARY_DISCORD_ID={selected[1][0]}")
    lines.append("NEXUS_RIG_IDENTITY_OWNERS_JSON=" + json.dumps(owners, separators=(",", ":")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-source", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--identity-env", type=Path, required=True)
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--production-schema-manifest", type=Path)
    args = parser.parse_args()

    legacy_source = args.legacy_source.resolve()
    target_dir = args.target_dir.resolve()
    identity_env = args.identity_env.resolve()

    if not legacy_source.is_file():
        raise SystemExit("legacy source database is missing")

    target_dir.mkdir(parents=True, exist_ok=True)
    if target_dir not in identity_env.parents:
        raise SystemExit("identity env must be inside the fixture target directory")

    legacy_target = target_dir / "legacy.sqlite"
    v5_target = target_dir / "v5.sqlite"
    for target in (legacy_target, v5_target):
        if target.exists():
            target.unlink()

    _online_backup(legacy_source, legacy_target)
    sqlite3.connect(v5_target).close()

    production_root = _resolve_production_root(target_dir, args.production_root)
    schema_manifest = _resolve_schema_manifest(target_dir, args.production_schema_manifest)
    schema_compatibility = _ensure_snapshot_schema_compatibility(
        legacy_target,
        schema_manifest,
    )
    traits_v2 = _ensure_trait_fixture(legacy_target, production_root)
    cognitive_nodes = _ensure_cognitive_nodes_fixture(legacy_target, production_root)

    legacy_integrity = _integrity(legacy_target)
    v5_integrity = _integrity(v5_target)
    if legacy_integrity != "ok" or v5_integrity != "ok":
        raise SystemExit("fixture database preparation failed integrity check")

    linked = _linked_identities(legacy_target)
    _write_identity_env(identity_env, linked)

    print(
        json.dumps(
            {
                "status": "PREPARED",
                "classification": "DEVELOPMENT_FIXTURE",
                "legacy_integrity": legacy_integrity,
                "v5_integrity": v5_integrity,
                "legacy_source_copied": True,
                "fresh_v5_state_created": True,
                "linked_identity_count": len(linked),
                "fixture_owner_fallback_enabled": bool(linked),
                "canonical_identity_acceptance": False,
                "source_state_mutated": False,
                "identity_values_emitted": False,
                "fixture_repairs": {
                    "production_schema_compatibility": schema_compatibility,
                    "traits_v2": traits_v2,
                    "CognitiveNodes": cognitive_nodes,
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
