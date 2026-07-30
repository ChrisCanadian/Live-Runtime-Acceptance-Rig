"""UTF-8 NDJSON tracing with protected-text metadata and redaction."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .redaction import Redactor


class Tracer:
    def __init__(
        self,
        output: Path,
        run_id: str,
        *,
        redactor: Redactor | None = None,
    ) -> None:
        self.output = output
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.redactor = redactor or Redactor(environment_values=())
        self._sequence = 0
        self._lock = threading.Lock()

    def emit(
        self,
        event: str,
        *,
        suite: str | None = None,
        case: str | None = None,
        **data: Any,
    ) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sequence": self._sequence,
                "run_id": self.run_id,
                "event": event,
            }
            if suite is not None:
                record["suite"] = suite
            if case is not None:
                record["case"] = case
            record.update(self.redactor.redact_value(data))
            with self.output.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return record

    @contextmanager
    def span(
        self,
        event: str,
        *,
        suite: str | None = None,
        case: str | None = None,
        **data: Any,
    ) -> Iterator[None]:
        started = time.perf_counter()
        self.emit(
            event,
            suite=suite,
            case=case,
            phase="started",
            **data,
        )
        try:
            yield
        except Exception as exc:
            self.emit(
                event,
                suite=suite,
                case=case,
                phase="completed",
                success=False,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                exception_type=type(exc).__name__,
            )
            raise
        else:
            self.emit(
                event,
                suite=suite,
                case=case,
                phase="completed",
                success=True,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
            )

    @staticmethod
    def protected_text_metadata(text: str) -> dict[str, Any]:
        encoded = text.encode("utf-8")
        return {
            "length": len(text),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
