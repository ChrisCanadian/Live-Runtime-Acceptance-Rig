from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "prepare_nexus_kernelized_fixture_state.py"
)


def _load_helper():
    spec = importlib.util.spec_from_file_location("nexus_fixture_schema_helper", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_reconstruction_creates_only_missing_empty_tables(tmp_path: Path):
    helper = _load_helper()
    database = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE Canary (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO Canary(value) VALUES ('preserve-me')")
        connection.commit()
    finally:
        connection.close()

    manifest = tmp_path / "production_snapshot_schema.json"
    manifest.write_text(
        json.dumps(
            {
                "Canary": [
                    {"name": "id", "type": "INTEGER", "notnull": 0, "pk": 1},
                    {"name": "value", "type": "TEXT", "notnull": 0, "pk": 0},
                ],
                "InteractionSummary": [
                    {"name": "InteractionID", "type": "INTEGER", "notnull": 0, "pk": 1},
                    {"name": "SummaryText", "type": "TEXT", "notnull": 0, "pk": 0},
                ],
                "GlobalTraits_Constants": [
                    {"name": "ConstantID", "type": "INTEGER", "notnull": 0, "pk": 1}
                ],
            }
        ),
        encoding="utf-8",
    )

    result = helper._ensure_snapshot_schema_compatibility(database, manifest)

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT value FROM Canary").fetchone() == ("preserve-me",)
        assert connection.execute(
            "SELECT COUNT(*) FROM InteractionSummary"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='GlobalTraits_Constants'"
        ).fetchone() is None
    finally:
        connection.close()

    assert result["created_empty_tables"] == ("InteractionSummary",)
    assert result["existing_tables_unchanged"] is True
    assert result["production_rows_invented"] is False


def test_trait_and_cognitive_seed_tables_are_migration_owned():
    helper = _load_helper()
    assert helper._SCHEMA_EXCLUSIONS == {
        "CognitiveNodes",
        "GlobalTraits_Constants",
        "GlobalTraits_Gauges",
        "UserTraitWeights",
    }
    source = SCRIPT.read_text(encoding="utf-8")
    assert "migrate_traits_v2.py" in source
    assert "migrate_010_global_cognitive_nodes.py" in source
    assert "production_snapshot_schema.json" in source
