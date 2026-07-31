"""Public API for the live runtime acceptance rig."""

from .assertions import AssertionLedger, Check, CheckStatus
from .config import RigConfig
from .contracts import (
    AcceptanceCase,
    CaseContext,
    CaseResult,
    CheckSpec,
    DatabaseAdapter,
    RuntimeAdapter,
)
from .runner import RigRunner, RunnerOptions

__all__ = [
    "AcceptanceCase",
    "AssertionLedger",
    "CaseContext",
    "CaseResult",
    "Check",
    "CheckSpec",
    "CheckStatus",
    "DatabaseAdapter",
    "RigConfig",
    "RigRunner",
    "RunnerOptions",
    "RuntimeAdapter",
]

__version__ = "0.1.1"
