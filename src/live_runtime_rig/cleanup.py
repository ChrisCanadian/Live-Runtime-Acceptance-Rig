"""Current-run cleanup manifest generation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .contracts import CleanupEntry


class CleanupManifest:
    def __init__(self, run_id: str, marker: str) -> None:
        self.run_id = run_id
        self.marker = marker
        self._entries: list[CleanupEntry] = []

    @property
    def entries(self) -> tuple[CleanupEntry, ...]:
        return tuple(self._entries)

    @staticmethod
    def _key(entry: CleanupEntry) -> tuple[str, str, str, str]:
        return (
            entry.resource_type,
            entry.identifier,
            entry.table_or_path,
            entry.run_marker,
        )

    def _validate(self, entry: CleanupEntry) -> None:
        if entry.run_marker != self.marker:
            raise ValueError("cleanup entry marker does not match the current run")
        if not entry.identifier or not entry.identifier.strip():
            raise ValueError("cleanup entry identifier must not be empty")

    def add(self, entry: CleanupEntry) -> None:
        self.add_many((entry,))

    def add_many(self, entries: Iterable[CleanupEntry]) -> None:
        """Validate an entire batch before adding its unique entries."""

        candidates = tuple(entries)
        for entry in candidates:
            self._validate(entry)

        known = {self._key(entry) for entry in self._entries}
        additions: list[CleanupEntry] = []
        for entry in candidates:
            key = self._key(entry)
            if key in known:
                continue
            known.add(key)
            additions.append(entry)
        self._entries.extend(additions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_marker": self.marker,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "automatic_cleanup_performed": False,
            "entries": [asdict(entry) for entry in self._entries],
        }