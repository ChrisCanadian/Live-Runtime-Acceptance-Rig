"""Configuration loading for CLI and programmatic use."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def _parse_bool(value: str, *, key: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be true or false")


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid configuration line {line_number}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        values[key] = value
    return values


def _resolve_path(base: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve()


@dataclass(frozen=True)
class RigConfig:
    config_file: Path
    runtime_adapter: str
    database_adapter: str
    cases: str
    database_path: Path
    evidence_dir: Path
    application_label: str = "application"
    public_safe: bool = False
    intentional_failure: bool = False

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> "RigConfig":
        resolved = path.resolve()
        values = _parse_env_file(resolved)
        environment = os.environ if environment is None else environment
        for key, value in environment.items():
            if key.startswith("RIG_"):
                values[key] = value
        required = (
            "RIG_RUNTIME_ADAPTER",
            "RIG_DATABASE_ADAPTER",
            "RIG_CASES",
            "RIG_DATABASE_PATH",
            "RIG_EVIDENCE_DIR",
        )
        missing = [key for key in required if not values.get(key)]
        if missing:
            raise ValueError(
                "Missing required configuration keys: " + ", ".join(missing)
            )
        base = resolved.parent
        return cls(
            config_file=resolved,
            runtime_adapter=values["RIG_RUNTIME_ADAPTER"],
            database_adapter=values["RIG_DATABASE_ADAPTER"],
            cases=values["RIG_CASES"],
            database_path=_resolve_path(base, values["RIG_DATABASE_PATH"]),
            evidence_dir=_resolve_path(base, values["RIG_EVIDENCE_DIR"]),
            application_label=values.get("RIG_APPLICATION_LABEL", "application"),
            public_safe=_parse_bool(
                values.get("RIG_PUBLIC_SAFE", "false"), key="RIG_PUBLIC_SAFE"
            ),
            intentional_failure=_parse_bool(
                values.get("RIG_INTENTIONAL_FAILURE", "false"),
                key="RIG_INTENTIONAL_FAILURE",
            ),
        )

    def case_settings(self) -> dict[str, object]:
        return {
            "application_label": self.application_label,
            "intentional_failure": self.intentional_failure,
        }
