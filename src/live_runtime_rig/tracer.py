"""UTF-8 NDJSON tracing with protected-text metadata and redaction."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .redaction import Redactor


class Tracer:
    RESERVED_FIELDS = frozenset(
        {"timestamp", "sequence", "run_id", "event", "suite", "case"}
    )

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
        self._protected_hash_key = secrets.token_bytes(32)

    def emit(self, event: str, **data: Any) -> dict[str, Any]:
        """Emit case data without allowing it to set runtime-owned metadata."""

        return self._emit(event, suite=None, case=None, data=data)

    def _emit(
        self,
        event: str,
        *,
        suite: str | None,
        case: str | None,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        collisions = self.RESERVED_FIELDS.intersection(data)
        if collisions:
            names = ", ".join(sorted(collisions))
            raise ValueError(f"trace data contains reserved fields: {names}")
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
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
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
        self._emit(
            event,
            suite=suite,
            case=case,
            data={"phase": "started", **data},
        )
        try:
            yield
        except Exception as exc:
            self._emit(
                event,
                suite=suite,
                case=case,
                data={
                    "phase": "completed",
                    "success": False,
                    "elapsed_ms": round(
                        (time.perf_counter() - started) * 1000,
                        3,
                    ),
                    "exception_type": type(exc).__name__,
                },
            )
            raise
        else:
            self._emit(
                event,
                suite=suite,
                case=case,
                data={
                    "phase": "completed",
                    "success": True,
                    "elapsed_ms": round(
                        (time.perf_counter() - started) * 1000,
                        3,
                    ),
                },
            )

    def protected_text_metadata(self, text: str) -> dict[str, Any]:
        encoded = text.encode("utf-8")
        return {
            "length": len(text),
            "hmac_sha256": hmac.new(
                self._protected_hash_key,
                encoded,
                hashlib.sha256,
            ).hexdigest(),
        }