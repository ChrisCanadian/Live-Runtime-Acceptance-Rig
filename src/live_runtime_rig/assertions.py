"""Explicit PASS, FAIL, and SKIP accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class Check:
    suite: str
    name: str
    status: CheckStatus
    expected: Any
    observed: Any
    evidence_path: str | None
    heuristic: bool
    timestamp: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


class AssertionLedger:
    """Collects explicit checks without inferring acceptance from truthiness."""

    def __init__(self) -> None:
        self._checks: list[Check] = []

    @property
    def checks(self) -> tuple[Check, ...]:
        return tuple(self._checks)

    def record(
        self,
        *,
        suite: str,
        name: str,
        status: CheckStatus,
        expected: Any,
        observed: Any,
        evidence_path: str | None = None,
        heuristic: bool = False,
    ) -> Check:
        if not isinstance(status, CheckStatus):
            raise TypeError("status must be a CheckStatus")
        check = Check(
            suite=suite,
            name=name,
            status=status,
            expected=expected,
            observed=observed,
            evidence_path=evidence_path,
            heuristic=heuristic,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._checks.append(check)
        return check

    @property
    def failed(self) -> bool:
        return any(check.status is CheckStatus.FAIL for check in self._checks)

    def summary(self) -> dict[str, int]:
        return {
            "total": len(self._checks),
            "passed": sum(c.status is CheckStatus.PASS for c in self._checks),
            "failed": sum(c.status is CheckStatus.FAIL for c in self._checks),
            "skipped": sum(c.status is CheckStatus.SKIP for c in self._checks),
        }
