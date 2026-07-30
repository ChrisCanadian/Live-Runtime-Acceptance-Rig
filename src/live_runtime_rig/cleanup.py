"""Current-run cleanup manifest generation."""

from __future__ import annotations

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

    def add(self, entry: CleanupEntry) -> None:
        if entry.run_marker != self.marker:
            raise ValueError("cleanup entry marker does not match the current run")
        self._entries.append(entry)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_marker": self.marker,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "automatic_cleanup_performed": False,
            "entries": [asdict(entry) for entry in self._entries],
        }
