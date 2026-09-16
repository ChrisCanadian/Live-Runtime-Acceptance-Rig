from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path


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
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
