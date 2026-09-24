#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


SNAPSHOT_PREFIX = "migration_staging/v5_snapshot"


def _git_bytes(repo: Path, commit: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "blob", f"{commit}:{path}"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def _git_blob_sha(data: bytes) -> str:
    payload = f"blob {len(data)}\0".encode("utf-8") + data
    return hashlib.sha1(payload).hexdigest()


def _manifest(repo: Path, commit: str) -> dict[str, Any]:
    raw = _git_bytes(repo, commit, f"{SNAPSHOT_PREFIX}/manifest.json")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("staged V5 manifest must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize the staged V5 snapshot from exact Git blob bytes. "
            "This avoids Windows checkout EOL conversion while preserving the "
            "NDKA runtime verifier as the final authority."
        )
    )
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    commit = args.commit.strip()
    manifest = _manifest(repo, commit)
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise SystemExit("staged V5 manifest contains no file closure")

    snapshot_root = repo / SNAPSHOT_PREFIX
    written = 0
    for item in files:
        if not isinstance(item, dict):
            raise SystemExit("malformed staged V5 manifest entry")
        relative = str(item.get("path") or "")
        expected_size = int(item.get("bytes"))
        expected_blob = str(item.get("git_blob_sha") or "")
        if not relative or not expected_blob:
            raise SystemExit("staged V5 manifest entry lacks path/blob SHA")

        object_path = f"{SNAPSHOT_PREFIX}/{relative}"
        data = _git_bytes(repo, commit, object_path)
        observed_blob = _git_blob_sha(data)
        if len(data) != expected_size:
            raise SystemExit(
                f"Git object size mismatch before materialization: {relative}; "
                f"expected {expected_size}, observed {len(data)}"
            )
        if observed_blob != expected_blob:
            raise SystemExit(
                f"Git object blob mismatch before materialization: {relative}; "
                f"expected {expected_blob}, observed {observed_blob}"
            )

        target = snapshot_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        reread = target.read_bytes()
        if len(reread) != expected_size or _git_blob_sha(reread) != expected_blob:
            raise SystemExit(
                f"materialized staged V5 file failed byte verification: {relative}"
            )
        written += 1

    manifest_bytes = _git_bytes(repo, commit, f"{SNAPSHOT_PREFIX}/manifest.json")
    (snapshot_root / "manifest.json").write_bytes(manifest_bytes)

    sample = snapshot_root / "migrations" / "0001_core.sql"
    sample_size = sample.stat().st_size if sample.is_file() else None
    print(
        json.dumps(
            {
                "status": "VERIFIED",
                "commit": commit,
                "file_count": written,
                "sample": "migrations/0001_core.sql",
                "sample_bytes": sample_size,
                "method": "git-cat-file-byte-materialization",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
